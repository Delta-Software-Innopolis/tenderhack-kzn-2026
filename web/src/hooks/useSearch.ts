import { useMutation } from '@tanstack/react-query'
import { analyzeQuery } from '../api/search'

export function useSearch() {
  return useMutation({ mutationFn: (query: string) => analyzeQuery(query) })
}
