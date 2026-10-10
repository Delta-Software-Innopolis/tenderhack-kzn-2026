import { useMutation } from '@tanstack/react-query'
import { searchItems } from '../api/search'

export function useSearch() {
  return useMutation({
    mutationFn: (query: string) => searchItems(query),
  })
}
