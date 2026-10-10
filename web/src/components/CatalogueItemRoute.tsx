import { useCatalogueItem } from '../hooks/useCatalogue'
import CatalogueItemPage from './CatalogueItemPage'

export default function CatalogueItemRoute({ code }: { code: string }) {
  const query = useCatalogueItem(code)

  if (query.isPending) {
    return <main className="route-state" role="status"><span className="search-form__spinner" />Загружаем карточку КТРУ…</main>
  }

  if (query.isError) {
    return (
      <main className="route-state route-state--error" role="alert">
        <h1>Карточка не загрузилась</h1><p>{query.error.message}</p>
        <a href="#catalogue">Вернуться к каталогу</a>
      </main>
    )
  }

  return <CatalogueItemPage item={query.data} />
}
