export type SourceSpan = { start: number; end: number }

export type OriginalValue =
  | { type: 'number'; value: number; unit: string | null }
  | { type: 'string'; value: string; unit: null }
  | { type: 'boolean'; value: boolean; unit: null }

export type NormalizedValue =
  | { type: 'number'; value: number; unit: { okei_code: string; name: string } | null }
  | { type: 'string'; value: string; unit: null }
  | { type: 'boolean'; value: boolean; unit: null }

export type CharacteristicOption = {
  characteristic_id: string
  name: string
  product_name?: string | null
  unit_names?: string[]
}

export type ExtractedAttribute = {
  id: string
  source_text: string
  source_span: SourceSpan
  mention_type: 'explicit' | 'implicit'
  status: 'resolved' | 'unknown' | 'needs_clarification'
  original_value: OriginalValue
  characteristic_id?: string | null
  characteristic_name?: string | null
  normalized_value?: NormalizedValue | null
  extracted_name?: string | null
  message?: string | null
  resolution_source?: 'model' | 'user'
  characteristic_options?: CharacteristicOption[]
}

export type Fact = {
  name: string
  type: 'string' | 'number' | 'boolean'
  value: string | number | boolean
  unit?: string | null
}

export type FunnelStep = { step: string; before: number; after: number }

export type HintOption = { label: string; fact: Fact; remaining: number }

export type AmbiguousHint = {
  name: string
  required: boolean
  avg: number
  options: HintOption[]
}

export type ConflictFix = {
  fact: Fact
  label: string
  drop: { remaining: number }
  options: Record<string, unknown>[]
  blocked_by_other_conflict: boolean
}

export type ConflictHint = {
  kind: 'conflict'
  facts: Fact[]
  message: string
  suggestions: unknown[]
  fixes: ConflictFix[]
}

export type Hint = ConflictHint | AmbiguousHint | Record<string, unknown>

export const isConflictHint = (h: Hint): h is ConflictHint =>
  'kind' in h && h.kind === 'conflict'

export const isAmbiguousHint = (h: Hint): h is AmbiguousHint =>
  'options' in h && 'required' in h && !('kind' in h)

export type AnalyzeStatus = 'resolved' | 'ambiguous' | 'conflict'

export type AnalyzeResponse = {
  funnel: FunnelStep[]
  candidates: string[]
  status: AnalyzeStatus
  result_code: string | null
  culprit: string | null
  hints: Hint[]
  attributes: ExtractedAttribute[]
}
