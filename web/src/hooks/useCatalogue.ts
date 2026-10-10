import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { getItem, listItems } from '../api/ktru'
import type { KtruCategory } from '../types/ktru'

export const CATALOGUE_PAGE_SIZE = 12

export function useCatalogue(page: number, category?: KtruCategory) {
  return useQuery({
    queryKey: ['catalogue', category ?? 'all', page],
    queryFn: () => listItems({
      offset: (page - 1) * CATALOGUE_PAGE_SIZE,
      limit: CATALOGUE_PAGE_SIZE,
      category,
    }),
    placeholderData: keepPreviousData,
  })
}

export function useCatalogueItem(code: string | null) {
  return useQuery({
    queryKey: ['catalogue-item', code],
    queryFn: () => getItem(code!),
    enabled: Boolean(code),
  })
}
