import type { CatalogueItem } from '../types/ktru'
import CatalogueCard from './CatalogueCard'

type CatalogueProps = {
  items: CatalogueItem[]
}

export default function Catalogue({ items }: CatalogueProps) {
  if (items.length === 0) {
    return (
      <div className="catalogue-empty" role="status">
        <span className="catalogue-empty__icon" aria-hidden="true">∅</span>
        <h3>В этой категории пока нет позиций</h3>
        <p>Попробуйте выбрать другую категорию.</p>
      </div>
    )
  }

  return (
    <div className="catalogue-grid">
      {items.map((item) => (
        <CatalogueCard item={item} key={item.id} />
      ))}
    </div>
  )
}
