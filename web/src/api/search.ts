import type {
  ClarificationSelection,
  ExtractApiResponse,
  ExtractResponse,
  OriginalValue,
  SearchResponse,
} from '../types/search'

const SEARCH_API_BASE_URL = import.meta.env.VITE_SEARCH_API_URL ?? '/search-api'
const EXTRACT_API_BASE_URL = import.meta.env.VITE_EXTRACT_API_URL ?? '/extract-api'

async function errorMessage(response: Response, fallback: string): Promise<string> {
  const body = await response.json().catch(() => null) as {
    detail?: string | { message?: string }
  } | null
  if (typeof body?.detail === 'string') return body.detail
  if (body?.detail && typeof body.detail.message === 'string') return body.detail.message
  return `${fallback}: ${response.status}`
}

export async function searchItems(query: string, limit = 10): Promise<SearchResponse> {
  const response = await fetch(`${SEARCH_API_BASE_URL}/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, limit }),
  })

  if (!response.ok) {
    throw new Error(await errorMessage(response, 'Ошибка поиска'))
  }

  return response.json() as Promise<SearchResponse>
}

export async function extractCharacteristics(searchResult: SearchResponse): Promise<ExtractApiResponse> {
  const response = await fetch(`${EXTRACT_API_BASE_URL}/extract`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(searchResult),
  })

  if (!response.ok) {
    throw new Error(await errorMessage(response, 'Ошибка разбора характеристик'))
  }
  return response.json() as Promise<ExtractApiResponse>
}

export async function betterSearch(query: string, limit = 10): Promise<ExtractResponse> {
  const searchResult = await searchItems(query, limit)
  const extraction = await extractCharacteristics(searchResult)
  return { ...extraction, candidates: searchResult.candidates }
}

function clarifiedValue(
  original: OriginalValue,
  kind: string,
  selected: string,
): OriginalValue {
  if (kind === 'specify_unit' && original.type === 'number') {
    return { ...original, unit: selected }
  }
  if (kind === 'specify_value' && original.type === 'number') {
    const parsed = Number(selected.replace(',', '.'))
    if (Number.isFinite(parsed)) return { ...original, value: parsed }
  }
  if (kind === 'specify_value' && original.type === 'boolean') {
    return { ...original, value: /^(да|true|1)$/i.test(selected) }
  }
  return { type: 'string', value: selected, unit: null }
}

export async function refineCharacteristics(
  result: ExtractResponse,
  selections: Record<string, ClarificationSelection>,
): Promise<ExtractResponse> {
  const clarificationByAttribute = new Map(
    (result.clarifications ?? []).map((clarification) => [clarification.attribute_id, clarification]),
  )
  const attributes = result.attributes.map((attribute) => {
    const clarification = clarificationByAttribute.get(attribute.id)
    const selection = clarification ? selections[clarification.id] : undefined
    if (!clarification || !selection) return attribute
    if (selection.type === 'characteristic') {
      return {
        ...attribute,
        characteristic_id: selection.characteristicId,
        resolution_source: 'user' as const,
      }
    }
    return {
      ...attribute,
      original_value: clarifiedValue(attribute.original_value, clarification.kind, selection.value),
      resolution_source: 'user' as const,
    }
  })
  const { candidates, ...extraction } = result
  const response = await fetch(`${EXTRACT_API_BASE_URL}/extract`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ...extraction,
      candidates,
      attributes,
      clarifications: [],
      issues: result.issues ?? [],
      status: 'pending',
    }),
  })
  if (!response.ok) throw new Error(await errorMessage(response, 'Ошибка уточнения характеристик'))
  const refined = await response.json() as ExtractApiResponse
  return { ...refined, candidates }
}
