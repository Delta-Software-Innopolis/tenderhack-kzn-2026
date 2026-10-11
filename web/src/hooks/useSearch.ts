import { useMutation } from '@tanstack/react-query'
import { betterSearch, refineCharacteristics } from '../api/search'
import type { ClarificationSelection, ExtractResponse } from '../types/search'

export function useSearch() {
  return useMutation({
    mutationFn: (query: string) => betterSearch(query),
  })
}

export function useRefineSearch() {
  return useMutation({
    mutationFn: ({ result, selections }: {
      result: ExtractResponse
      selections: Record<string, ClarificationSelection>
    }) => refineCharacteristics(result, selections),
  })
}
