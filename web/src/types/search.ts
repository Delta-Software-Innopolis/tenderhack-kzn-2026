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
