import type { CatalogueItem } from '../types/ktru'

const statusLabels: Record<string, string> = {
  ACTIVE: 'Действует',
  INACTIVE: 'Не действует',
  TERMINATED: 'Прекращена',
}

type CatalogueCardProps = {
  item: CatalogueItem
}

export default function CatalogueCard({ item }: CatalogueCardProps) {
  return (
    <article className="catalogue-card">
      <div className="catalogue-card__topline">
        <span className={`catalogue-card__status catalogue-card__status--${item.status?.toLowerCase() ?? 'unknown'}`}>
          {item.status ? statusLabels[item.status] ?? item.status : 'Статус неизвестен'}
        </span>
        <span className="catalogue-card__version">Версия {item.version}</span>
      </div>

      <h3>{item.name ?? 'Без наименования'}</h3>
      <p className="catalogue-card__code">
        <span>Код КТРУ</span>
        {item.code}
      </p>

      <p className="catalogue-card__okpd">
        <span>ОКПД-2 {item.okpd2_code ?? '—'}</span>
        {item.okpd2_name ?? 'Наименование не указано'}
      </p>

      <div className="catalogue-card__bottom">
        <span>{item.characteristics.length} характеристик</span>
        <a href={`#/catalogue/${encodeURIComponent(item.code)}`}>Подробнее <span aria-hidden="true">→</span></a>
      </div>
    </article>
  )
}
