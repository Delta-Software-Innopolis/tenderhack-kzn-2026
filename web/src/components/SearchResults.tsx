import type { SearchResponse } from '../types/search'

const statusLabels: Record<string, string> = {
  ACTIVE: 'Действует',
  INACTIVE: 'Не действует',
  TERMINATED: 'Прекращена',
}

type SearchResultsProps = {
  result: SearchResponse
}

export default function SearchResults({ result }: SearchResultsProps) {
  return (
    <section className="search-results" id="search-results" aria-labelledby="search-results-title">
      <div className="search-results__heading">
        <div>
          <p className="eyebrow">Результаты поиска</p>
          <h2 id="search-results-title">Подходящие позиции КТРУ</h2>
        </div>
        <p>
          Запрос распознан как: <strong>{result.canonical_query}</strong>
        </p>
      </div>

      {result.candidates.length === 0 ? (
        <div className="catalogue-empty" role="status">
          <span className="catalogue-empty__icon" aria-hidden="true">∅</span>
          <h3>Подходящие позиции не найдены</h3>
          <p>Попробуйте изменить формулировку или добавить характеристики товара.</p>
        </div>
      ) : (
        <div className="catalogue-grid">
          {result.candidates.filter(c=>!c.is_template).map((candidate) => (
            <article className="catalogue-card search-result-card" key={candidate.ktru_code}>
              <div className="catalogue-card__topline">
                <span className={`catalogue-card__status catalogue-card__status--${candidate.status?.toLowerCase() ?? 'unknown'}`}>
                  {candidate.status ? statusLabels[candidate.status] ?? candidate.status : 'Статус неизвестен'}
                </span>
                {candidate.rrf_score !== undefined && (
                  <span className="catalogue-card__version">
                    Релевантность {(candidate.rrf_score * 100).toFixed(2)}
                  </span>
                )}
              </div>
              <h3>{candidate.name ?? 'Без наименования'}</h3>
              <p className="catalogue-card__code">
                <span>Код КТРУ</span>
                {candidate.ktru_code}
              </p>
              <p className="catalogue-card__okpd">
                <span>ОКПД-2</span>
                {candidate.okpd2_code ?? 'Не указан'}
              </p>
              <div className="catalogue-card__bottom">
                <span>Результат поиска</span>
                <a href={`#/catalogue/${encodeURIComponent(candidate.ktru_code)}`}>
                  Подробнее <span aria-hidden="true">→</span>
                </a>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  )
}
