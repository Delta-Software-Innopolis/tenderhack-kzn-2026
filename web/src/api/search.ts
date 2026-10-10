import type { SearchResponse } from '../types/search'

const SEARCH_API_BASE_URL = import.meta.env.VITE_SEARCH_API_URL ?? '/search-api'

export async function searchItems(query: string, limit = 10): Promise<SearchResponse> {
  const response = await fetch(`${SEARCH_API_BASE_URL}/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, limit }),
  })

  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null
    throw new Error(typeof body?.detail === 'string' ? body.detail : `Ошибка поиска: ${response.status}`)
  }

  return response.json() as Promise<SearchResponse>
}
