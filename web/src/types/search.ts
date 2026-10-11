export type SearchCandidate = {
  ktru_code: string
  name?: string | null
  status?: string | null
  okpd2_code?: string | null
  rrf_score?: number
  is_template: boolean
}

export type SearchResponse = {
  query: string
  canonical_query: string
  lemmatized_query: string
  candidates: SearchCandidate[]
}

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

export type Clarification = {
  id: string
  attribute_id: string
  kind: 'choose_characteristic' | 'specify_unit' | 'specify_value'
  question: string
  options?: CharacteristicOption[]
  suggested_values?: string[]
}

export type ExtractionIssue = {
  id: string
  code: string
  message: string
  blocking: boolean
  attribute_id?: string | null
  candidate_code?: string | null
  source_text?: string | null
  source_span?: SourceSpan | null
}

export type ExtractApiResponse = {
  schema_version: '1.0'
  search_target: string | null
  query: string
  canonical_query: string
  lemmatized_query: string
  attributes: ExtractedAttribute[]
  clarifications?: Clarification[]
  issues?: ExtractionIssue[]
  status: 'completed' | 'needs_clarification'
  input_fingerprint?: string | null
}

export type ExtractResponse = ExtractApiResponse & {
  candidates: SearchCandidate[]
}

export type ClarificationSelection =
  | { type: 'characteristic'; characteristicId: string }
  | { type: 'suggested_value'; value: string }
