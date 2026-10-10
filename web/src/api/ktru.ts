import type { CatalogueItem, KtruCategory } from '../types/ktru'

const API_BASE_URL = import.meta.env.VITE_API_URL ?? '/api'

async function apiRequest<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`)
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as { detail?: string }
    throw new Error(body.detail ?? `Ошибка API: ${response.status}`)
  }
  return response.json() as Promise<T>
}

export function listItems(params: { offset: number; limit: number; category?: KtruCategory }) {
  const searchParams = new URLSearchParams({
    offset: String(params.offset),
    limit: String(params.limit),
  })
  if (params.category) searchParams.set('category', params.category)
  return apiRequest<CatalogueItem[]>(`/items/?${searchParams}`)
}

export function countItems(category?: KtruCategory) {
  const searchParams = new URLSearchParams()
  if (category) searchParams.set('category', category)
  const query = searchParams.size > 0 ? `?${searchParams}` : ''
  return apiRequest<{ count: number }>(`/items/count${query}`)
}

export function getItem(code: string) {
  return apiRequest<CatalogueItem>(`/item/${encodeURIComponent(code)}`)
}
