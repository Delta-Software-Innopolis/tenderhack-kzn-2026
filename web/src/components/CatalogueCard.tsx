import type { CatalogueItem } from '../types/ktru'

const categoryLabels: Record<CatalogueItem['category'], string> = {
  tools: 'Инструменты',
  furniture: 'Мебель',
  clothing: 'Одежда',
}

type CatalogueCardProps = {
  item: CatalogueItem
}

export default function CatalogueCard({ item }: CatalogueCardProps) {
  return (
    <article className="catalogue-card">
      <div className="catalogue-card__topline">
        <span className={`catalogue-card__category catalogue-card__category--${item.category}`}>
          {categoryLabels[item.category]}
        </span>
        <span className="catalogue-card__demo">Демо</span>
      </div>

      <h3>{item.name}</h3>
      <p className="catalogue-card__code">
        <span>{item.code.startsWith('ДЕМО-') ? 'Демо-код' : 'Код КТРУ'}</span>
        {item.code}
      </p>

      <p className="catalogue-card__okpd">
        <span>ОКПД-2 {item.okpd2.code}</span>
        {item.okpd2.name}
      </p>

      <div className="catalogue-card__bottom">
        <span>{item.unit.name} ({item.unit.symbol})</span>
        <a href={`#/catalogue/${encodeURIComponent(item.id)}`}>Подробнее <span aria-hidden="true">→</span></a>
      </div>
    </article>
  )
}
