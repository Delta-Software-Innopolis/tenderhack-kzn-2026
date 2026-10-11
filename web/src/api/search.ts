import type { AnalyzeResponse } from '../types/search'

const SEARCH_API_BASE_URL = import.meta.env.VITE_SEARCH_API_URL ?? '/search-api'

async function errorMessage(response: Response, fallback: string): Promise<string> {
  const body = await response.json().catch(() => null) as { detail?: unknown } | null
  const detail = body?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const msg = detail.map((d) => (d as { msg?: string }).msg ?? '').filter(Boolean).join('; ')
    if (msg) return msg
  }
  return `${fallback}: ${response.status}`
}

export async function analyzeQuery(query: string): Promise<AnalyzeResponse> {
  const response = await fetch(`${SEARCH_API_BASE_URL}/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query }),
  })
  if (!response.ok) throw new Error(await errorMessage(response, 'Ошибка поиска'))
  return response.json() as Promise<AnalyzeResponse>
}
