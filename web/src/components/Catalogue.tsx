import type { Category } from './CategoryFilters'
import { CATALOGUE_PAGE_SIZE, useCatalogue } from '../hooks/useCatalogue'
import type { KtruCategory } from '../types/ktru'
import type { CatalogueItem } from '../types/ktru'
import CatalogueCard from './CatalogueCard'

type CatalogueProps = {
  category: Category
  page: number
  onPageChange: (page: number) => void
}

const apiCategoryByFilter: Partial<Record<Category, KtruCategory>> = {
  tools: 'инструменты',
  furniture: 'мебель',
  clothing: 'одежда',
}

export default function Catalogue({ category, page, onPageChange }: CatalogueProps) {
  const query = useCatalogue(page, apiCategoryByFilter[category])
  const items: CatalogueItem[] = query.data ?? []

  if (query.isPending) {
    return (
      <div className="catalogue-loading" role="status">
        <span className="search-form__spinner" aria-hidden="true" />
        Загружаем позиции КТРУ…
      </div>
    )
  }

  if (query.isError) {
    return (
      <div className="catalogue-empty catalogue-error" role="alert">
        <h3>Не удалось загрузить каталог</h3>
        <p>{query.error.message}</p>
        <button type="button" onClick={() => void query.refetch()}>Попробовать снова</button>
      </div>
    )
  }

  if (items.length === 0) {
    return (
      <div className="catalogue-empty" role="status">
        <span className="catalogue-empty__icon" aria-hidden="true">∅</span>
        <h3>В этой категории пока нет позиций</h3>
        <p>{page > 1 ? 'Это последняя страница каталога.' : 'Попробуйте выбрать другую категорию.'}</p>
        {page > 1 && <button type="button" onClick={() => onPageChange(page - 1)}>Вернуться назад</button>}
      </div>
    )
  }

  return (
    <>
      <div className="catalogue-result-meta" aria-live="polite">
        Страница {page} · позиций на странице: {items.length}
      </div>
      <div className={`catalogue-grid${query.isPlaceholderData ? ' is-updating' : ''}`}>
        {items.map((item) => <CatalogueCard item={item} key={item.code} />)}
      </div>
      <nav className="catalogue-pagination" aria-label="Страницы каталога">
        <button type="button" disabled={page === 1 || query.isFetching} onClick={() => onPageChange(page - 1)}>
          <span aria-hidden="true">←</span> Назад
        </button>
        {page > 1 && <button type="button" onClick={() => onPageChange(page - 1)}>{page - 1}</button>}
        <span className="catalogue-pagination__current" aria-current="page">{page}</span>
        {items.length === CATALOGUE_PAGE_SIZE && (
          <button type="button" onClick={() => onPageChange(page + 1)}>{page + 1}</button>
        )}
        <button
          type="button"
          disabled={items.length < CATALOGUE_PAGE_SIZE || query.isFetching}
          onClick={() => onPageChange(page + 1)}
        >
          Вперёд <span aria-hidden="true">→</span>
        </button>
      </nav>
    </>
  )
}
