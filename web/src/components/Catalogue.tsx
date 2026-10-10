import { useEffect } from 'react'
import CategoryFilters, { type Category } from './CategoryFilters'
import { CATALOGUE_PAGE_SIZE, useCatalogue, useCatalogueCount } from '../hooks/useCatalogue'
import type { KtruCategory } from '../types/ktru'
import type { CatalogueItem } from '../types/ktru'
import CatalogueCard from './CatalogueCard'

type CatalogueProps = {
  category: Category
  page: number
  onCategoryChange: (category: Category) => void
  onPageChange: (page: number) => void
}

const apiCategoryByFilter: Partial<Record<Category, KtruCategory>> = {
  tools: 'инструменты',
  furniture: 'мебель',
  clothing: 'одежда',
}

type PaginationProps = {
  page: number
  totalPages: number
  isFetching: boolean
  position: 'top' | 'bottom'
  onPageChange: (page: number) => void
}

function Pagination({ page, totalPages, isFetching, position, onPageChange }: PaginationProps) {
  return (
    <nav
      className={`catalogue-pagination catalogue-pagination--${position}`}
      aria-label={`Страницы каталога, навигация ${position === 'top' ? 'сверху' : 'снизу'}`}
    >
      {page > 1 && (
        <button type="button" disabled={isFetching} onClick={() => onPageChange(page - 1)}>
          <span aria-hidden="true">←</span> Назад
        </button>
      )}
      {page > 1 && (
        <button type="button" aria-label="Первая страница" onClick={() => onPageChange(1)}>1</button>
      )}
      {page > 2 && <span className="catalogue-pagination__ellipsis" aria-hidden="true">…</span>}
      <span className="catalogue-pagination__current" aria-current="page">{page}</span>
      {page < totalPages - 1 && (
        <span className="catalogue-pagination__ellipsis" aria-hidden="true">…</span>
      )}
      {page < totalPages && (
        <button type="button" aria-label="Последняя страница" onClick={() => onPageChange(totalPages)}>
          {totalPages}
        </button>
      )}
      {page < totalPages && (
        <button type="button" disabled={isFetching} onClick={() => onPageChange(page + 1)}>
          Вперёд <span aria-hidden="true">→</span>
        </button>
      )}
    </nav>
  )
}

export default function Catalogue({ category, page, onCategoryChange, onPageChange }: CatalogueProps) {
  const apiCategory = apiCategoryByFilter[category]
  const query = useCatalogue(page, apiCategory)
  const countQuery = useCatalogueCount(apiCategory)
  const items: CatalogueItem[] = query.data ?? []
  const totalItems = countQuery.data?.count ?? 0
  const totalPages = Math.ceil(totalItems / CATALOGUE_PAGE_SIZE)
  const isFetching = query.isFetching || countQuery.isFetching
  const toolbar = (showPagination: boolean) => (
    <div className="catalogue-toolbar">
      <CategoryFilters value={category} onChange={onCategoryChange} />
      {showPagination && (
        <Pagination
          page={page}
          totalPages={totalPages}
          isFetching={isFetching}
          position="top"
          onPageChange={onPageChange}
        />
      )}
    </div>
  )

  useEffect(() => {
    if (totalPages > 0 && page > totalPages) onPageChange(totalPages)
  }, [onPageChange, page, totalPages])

  if (query.isPending || countQuery.isPending) {
    return (
      <>
        {toolbar(false)}
        <div className="catalogue-loading" role="status">
          <span className="search-form__spinner" aria-hidden="true" />
          Загружаем позиции КТРУ…
        </div>
      </>
    )
  }

  if (query.isError || countQuery.isError) {
    const error = query.error ?? countQuery.error
    return (
      <>
        {toolbar(false)}
        <div className="catalogue-empty catalogue-error" role="alert">
          <h3>Не удалось загрузить каталог</h3>
          <p>{error?.message}</p>
          <button type="button" onClick={() => void Promise.all([query.refetch(), countQuery.refetch()])}>
            Попробовать снова
          </button>
        </div>
      </>
    )
  }

  if (items.length === 0) {
    return (
      <>
        {toolbar(false)}
        <div className="catalogue-empty" role="status">
          <span className="catalogue-empty__icon" aria-hidden="true">∅</span>
          <h3>В этой категории пока нет позиций</h3>
          <p>{page > 1 ? 'Это последняя страница каталога.' : 'Попробуйте выбрать другую категорию.'}</p>
          {page > 1 && <button type="button" onClick={() => onPageChange(page - 1)}>Вернуться назад</button>}
        </div>
      </>
    )
  }

  return (
    <>
      {toolbar(true)}
      <div className="catalogue-result-meta" aria-live="polite">
        Страница {page} из {totalPages} · всего позиций: {totalItems}
      </div>
      <div className={`catalogue-grid${query.isPlaceholderData ? ' is-updating' : ''}`}>
        {items.map((item) => <CatalogueCard item={item} key={item.code} />)}
      </div>
      <Pagination
        page={page}
        totalPages={totalPages}
        isFetching={isFetching}
        position="bottom"
        onPageChange={onPageChange}
      />
    </>
  )
}
