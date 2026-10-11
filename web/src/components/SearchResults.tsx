import { useState } from 'react'
import type {
  ClarificationSelection,
  ExtractResponse,
  NormalizedValue,
  OriginalValue,
  SearchCandidate,
} from '../types/search'
import { useCatalogueItem } from '../hooks/useCatalogue'
import CatalogueCard from './CatalogueCard'

const statusLabels: Record<string, string> = {
  ACTIVE: 'Действует',
  INACTIVE: 'Не действует',
  TERMINATED: 'Прекращена',
}

const attributeStatusLabels = {
  resolved: 'Сопоставлено с КТРУ',
  unknown: 'Неизвестная характеристика',
  needs_clarification: 'Нужно уточнение',
}

function formatOriginalValue(value: OriginalValue): string {
  if (value.type === 'boolean') return value.value ? 'Да' : 'Нет'
  return `${value.value}${value.unit ? ` ${value.unit}` : ''}`
}

function formatNormalizedValue(value: NormalizedValue): string {
  if (value.type === 'boolean') return value.value ? 'Да' : 'Нет'
  if (value.type === 'number') return `${value.value}${value.unit ? ` ${value.unit.name}` : ''}`
  return value.value
}

type SearchResultsProps = {
  result: ExtractResponse
  isRefining: boolean
  onRefine: (selections: Record<string, ClarificationSelection>) => void
}

function SearchCandidateCard({ candidate }: { candidate: SearchCandidate }) {
  const itemQuery = useCatalogueItem(candidate.ktru_code)
  const relevance = candidate.rrf_score === undefined
    ? 'Результат поиска'
    : `Релевантность ${(candidate.rrf_score * 100).toFixed(2)}`

  if (itemQuery.data) {
    return <CatalogueCard item={itemQuery.data} secondaryLabel={relevance} />
  }

  return (
    <article className="catalogue-card search-result-card">
      <div className="catalogue-card__topline">
        <span className={`catalogue-card__status catalogue-card__status--${candidate.status?.toLowerCase() ?? 'unknown'}`}>
          {candidate.status ? statusLabels[candidate.status] ?? candidate.status : 'Статус неизвестен'}
        </span>
        <span className="catalogue-card__version">{relevance}</span>
      </div>
      <h3>{candidate.name ?? 'Без наименования'}</h3>
      <p className="catalogue-card__code"><span>Код КТРУ</span>{candidate.ktru_code}</p>
      <p className="catalogue-card__okpd"><span>ОКПД-2</span>{candidate.okpd2_code ?? 'Не указан'}</p>
      <div className="catalogue-card__bottom">
        <span>{itemQuery.isError ? 'Характеристики недоступны' : 'Загружаем характеристики…'}</span>
        <a href={`#/catalogue/${encodeURIComponent(candidate.ktru_code)}`}>Подробнее <span aria-hidden="true">→</span></a>
      </div>
    </article>
  )
}

export default function SearchResults({ result, isRefining, onRefine }: SearchResultsProps) {
  const candidates = result.candidates.filter((candidate) => !candidate.is_template)
  const clarifications = result.clarifications ?? []
  const issues = result.issues ?? []
  const [selections, setSelections] = useState<Record<string, ClarificationSelection>>({})
  const canRefine = clarifications.length > 0
    && clarifications.every((clarification) => selections[clarification.id] !== undefined)

  return (
    <section className="search-results" id="search-results" aria-labelledby="search-results-title">
      <div className="search-results__heading">
        <div>
          <p className="eyebrow">Интеллектуальный разбор</p>
          <h2 id="search-results-title">Мы поняли ваш запрос</h2>
        </div>
        <div className={`extraction-status extraction-status--${result.status}`}>
          {result.status === 'completed' ? 'Разбор завершён' : 'Требуется уточнение'}
        </div>
      </div>

      <div className="query-understanding">
        <span>Исходный запрос</span>
        <strong>«{result.query}»</strong>
        {result.search_target && (
          <div className="query-understanding__target">
            <span>Искомый товар</span>
            <strong>{result.search_target}</strong>
          </div>
        )}
        {result.canonical_query !== result.query && (
          <p>Каноническая формулировка: {result.canonical_query}</p>
        )}
      </div>

      {result.attributes.length > 0 && (
        <div className="extracted-attributes">
          <div className="results-subheading">
            <h3>Выделенные характеристики</h3>
            <span>{result.attributes.length}</span>
          </div>
          <div className="extracted-attributes__grid">
            {result.attributes.map((attribute) => (
              <article className={`extracted-attribute extracted-attribute--${attribute.status}`} key={attribute.id}>
                <div className="extracted-attribute__topline">
                  <span>{attribute.mention_type === 'explicit' ? 'Явно указано' : 'Определено из контекста'}</span>
                  <span>{attributeStatusLabels[attribute.status]}</span>
                </div>
                <h4>{attribute.characteristic_name ?? attribute.extracted_name ?? attribute.source_text}</h4>
                <div className="extracted-attribute__value">
                  <span>{formatOriginalValue(attribute.original_value)}</span>
                  {attribute.normalized_value && (
                    <><span aria-hidden="true">→</span><strong>{formatNormalizedValue(attribute.normalized_value)}</strong></>
                  )}
                </div>
                <p className="extracted-attribute__source">Фрагмент: «{attribute.source_text}»</p>
                {attribute.message && <p className="extracted-attribute__message">{attribute.message}</p>}
              </article>
            ))}
          </div>
        </div>
      )}

      {clarifications.length > 0 && (
        <div className="clarifications" role="status">
          <div className="results-subheading"><h3>Нужно уточнить</h3><span>{clarifications.length}</span></div>
          {clarifications.map((clarification) => (
            <article className="clarification" key={clarification.id}>
              <strong>{clarification.question}</strong>
              {clarification.options && clarification.options.length > 0 && (
                <div className="clarification__options">
                  {clarification.options.map((option) => {
                    const selected = selections[clarification.id]
                    const isSelected = selected?.type === 'characteristic'
                      && selected.characteristicId === option.characteristic_id
                    return (
                      <button
                        className={isSelected ? 'is-selected' : ''}
                        type="button"
                        aria-pressed={isSelected}
                        key={option.characteristic_id}
                        onClick={() => setSelections((current) => ({
                          ...current,
                          [clarification.id]: {
                            type: 'characteristic',
                            characteristicId: option.characteristic_id,
                          },
                        }))}
                      >
                        {option.name}
                      </button>
                    )
                  })}
                </div>
              )}
              {clarification.suggested_values && clarification.suggested_values.length > 0 && (
                <div className="clarification__options">
                  {clarification.suggested_values.map((value) => {
                    const selected = selections[clarification.id]
                    const isSelected = selected?.type === 'suggested_value' && selected.value === value
                    return (
                      <button
                        className={isSelected ? 'is-selected' : ''}
                        type="button"
                        aria-pressed={isSelected}
                        key={value}
                        onClick={() => setSelections((current) => ({
                          ...current,
                          [clarification.id]: { type: 'suggested_value', value },
                        }))}
                      >
                        {value}
                      </button>
                    )
                  })}
                </div>
              )}
            </article>
          ))}
          <button
            className="clarifications__submit"
            type="button"
            disabled={!canRefine || isRefining}
            onClick={() => onRefine(selections)}
          >
            {isRefining ? 'Применяем уточнения…' : 'Применить уточнения'}
          </button>
        </div>
      )}

      {issues.length > 0 && (
        <div className="extraction-issues" role="alert">
          {issues.map((issue) => <p className={issue.blocking ? 'is-blocking' : ''} key={issue.id}>{issue.message}</p>)}
        </div>
      )}

      <div className="candidate-results">
        <div className="results-subheading"><h3>Подходящие позиции КТРУ</h3><span>{candidates.length}</span></div>
        {candidates.length === 0 ? (
          <div className="catalogue-empty" role="status">
            <span className="catalogue-empty__icon" aria-hidden="true">∅</span>
            <h3>Подходящие позиции не найдены</h3>
            <p>Попробуйте изменить формулировку или добавить характеристики товара.</p>
          </div>
        ) : (
          <div className="catalogue-grid">
            {candidates.map((candidate) => <SearchCandidateCard candidate={candidate} key={candidate.ktru_code} />)}
          </div>
        )}
      </div>
    </section>
  )
}
