import { useQueries } from '@tanstack/react-query'
import { getItem } from '../api/ktru'
import {
  isAmbiguousHint,
  isConflictHint,
  type AnalyzeResponse,
  type ExtractedAttribute,
  type Fact,
  type NormalizedValue,
  type OriginalValue,
} from '../types/search'
import CatalogueCard from './CatalogueCard'

const statusTitles: Record<AnalyzeResponse['status'], string> = {
  resolved: 'Позиция найдена',
  ambiguous: 'Запрос слишком общий',
  conflict: 'Характеристики конфликтуют',
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

// --- query rewriting (backend only accepts a plain query string) ---

function appendFact(query: string, fact: Fact): string {
  if (fact.type === 'string') return `${query} ${fact.value}`.trim()
  if (fact.type === 'number') return `${query} ${fact.name} ${fact.value}`.trim()
  return `${query} ${fact.name}`.trim()
}

function cutSpan(query: string, start: number, end: number): string {
  return `${query.slice(0, start)} ${query.slice(end)}`.replace(/\s+/g, ' ').trim()
}

function dropFact(query: string, fact: Fact, attributes: ExtractedAttribute[]): string {
  const wanted = String(fact.value).toLowerCase()
  const attribute = attributes.find(
    (a) => String(a.normalized_value?.value ?? '').toLowerCase() === wanted,
  )
  if (attribute) {
    const { start, end } = attribute.source_span
    if (query.slice(start, end).toLowerCase() === attribute.source_text.toLowerCase()) {
      return cutSpan(query, start, end)
    }
  }
  const index = query.toLowerCase().indexOf(wanted)
  return index >= 0 ? cutSpan(query, index, index + wanted.length) : query
}

type SearchResultsProps = {
  result: AnalyzeResponse
  query: string
  isLoading: boolean
  onRequery: (query: string) => void
}

export default function SearchResults({ result, query, isLoading, onRequery }: SearchResultsProps) {
  const itemQueries = useQueries({
    queries: result.candidates.map((code) => ({
      queryKey: ['catalogue-item', code],
      queryFn: () => getItem(code),
      staleTime: 5 * 60_000,
    })),
  })

  const candidates = result.candidates
    .map((code, index) => ({ code, query: itemQueries[index] }))
    .filter(({ query: q }) => q.data?.is_template !== 1)

  const conflictHints = result.hints.filter(isConflictHint)
  const ambiguousHints = result.hints.filter(isAmbiguousHint)

  return (
    <section className="search-results" id="search-results" aria-labelledby="search-results-title">
      <div className="search-results__heading">
        <div>
          <p className="eyebrow">Интеллектуальный разбор</p>
          <h2 id="search-results-title">Мы поняли ваш запрос</h2>
        </div>
        <div className={`extraction-status extraction-status--${result.status}`}>
          {statusTitles[result.status]}
        </div>
      </div>

      <div className="query-understanding">
        <span>Исходный запрос</span>
        <strong>«{query}»</strong>
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

      {result.funnel.length > 0 && (
        <div className="funnel">
          <div className="results-subheading"><h3>Как сужался поиск</h3><span>{result.funnel.length}</span></div>
          <ol>
            {result.funnel.map((step, index) => (
              <li key={`${step.step}-${index}`}>
                <strong>{step.step}</strong> — {step.before} → {step.after}
              </li>
            ))}
          </ol>
        </div>
      )}

      {result.status === 'ambiguous' && ambiguousHints.length > 0 && (
        <div className="clarifications" role="status">
          <div className="results-subheading">
            <h3>Уточните запрос</h3><span>{ambiguousHints.length}</span>
          </div>
          {ambiguousHints.map((hint) => (
            <article className="clarification" key={hint.name}>
              <strong>{hint.name}{hint.required ? ' (обязательная)' : ''}</strong>
              <div className="clarification__options">
                {hint.options.map((option) => (
                  <button
                    type="button"
                    key={option.label}
                    disabled={isLoading}
                    title={`Останется позиций: ${option.remaining}`}
                    onClick={() => onRequery(appendFact(query, option.fact))}
                  >
                    {option.label} · {option.remaining}
                  </button>
                ))}
              </div>
            </article>
          ))}
        </div>
      )}

      {result.status === 'conflict' && conflictHints.map((hint, hintIndex) => (
        <div className="clarifications" role="alert" key={hintIndex}>
          <div className="results-subheading"><h3>Конфликт характеристик</h3></div>
          <p>{hint.message}</p>
          <div className="clarification__options">
            {hint.fixes.map((fix) => (
              <button
                type="button"
                key={fix.label}
                disabled={isLoading || fix.blocked_by_other_conflict}
                onClick={() => onRequery(dropFact(query, fix.fact, result.attributes))}
              >
                Убрать: {fix.label} · останется {fix.drop.remaining}
              </button>
            ))}
          </div>
        </div>
      ))}

      {result.status !== 'conflict' && (
        <div className="candidate-results">
          <div className="results-subheading">
            <h3>{result.status === 'resolved' ? 'Найденная позиция КТРУ' : 'Подходящие позиции КТРУ'}</h3>
            <span>{candidates.length}</span>
          </div>
          {candidates.length === 0 ? (
            <div className="catalogue-empty" role="status">
              <span className="catalogue-empty__icon" aria-hidden="true">∅</span>
              <h3>Подходящие позиции не найдены</h3>
              <p>Попробуйте изменить формулировку или добавить характеристики товара.</p>
            </div>
          ) : (
            <div className="catalogue-grid">
              {candidates.map(({ code, query: itemQuery }) => {
                const label = code === result.result_code ? 'Лучшее совпадение' : undefined
                if (itemQuery.data) {
                  return <CatalogueCard item={itemQuery.data} secondaryLabel={label} key={code} />
                }
                return (
                  <article className="catalogue-card search-result-card" key={code}>
                    <p className="catalogue-card__code"><span>Код КТРУ</span>{code}</p>
                    <div className="catalogue-card__bottom">
                      <span>{itemQuery.isError ? 'Характеристики недоступны' : 'Загружаем характеристики…'}</span>
                      <a href={`#/catalogue/${encodeURIComponent(code)}`}>Подробнее <span aria-hidden="true">→</span></a>
                    </div>
                  </article>
                )
              })}
            </div>
          )}
        </div>
      )}
    </section>
  )
}
