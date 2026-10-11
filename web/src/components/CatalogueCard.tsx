import type { CatalogueItem, KtruCharacteristicValue } from '../types/ktru'

const statusLabels: Record<string, string> = {
  ACTIVE: 'Действует',
  INACTIVE: 'Не действует',
  TERMINATED: 'Прекращена',
}

type CatalogueCardProps = {
  item: CatalogueItem
  secondaryLabel?: string
}

const notation: Record<string, string> = {
  greater: '>', greaterOrEqual: '≥', less: '<', lessOrEqual: '≤',
}

function formatValue(value: KtruCharacteristicValue): string {
  const unit = value.okei_name ? ` ${value.okei_name}` : ''
  if (value.quality_description) return value.quality_description
  if (value.concrete_value !== null) return `${value.concrete_value}${unit}`
  const bounds = []
  if (value.min_value !== null) bounds.push(`${notation[value.min_notation ?? ''] ?? ''} ${value.min_value}`.trim())
  if (value.max_value !== null) bounds.push(`${notation[value.max_notation ?? ''] ?? ''} ${value.max_value}`.trim())
  return bounds.length > 0 ? `${bounds.join(' · ')}${unit}` : 'Значение не указано'
}

export default function CatalogueCard({ item, secondaryLabel }: CatalogueCardProps) {
  const requiredCharacteristics = item.characteristics.filter((characteristic) => characteristic.is_required === 1)
  const visibleRequired = requiredCharacteristics.slice(0, 4)

  return (
    <article className="catalogue-card">
      <div className="catalogue-card__topline">
        <span className={`catalogue-card__status catalogue-card__status--${item.status?.toLowerCase() ?? 'unknown'}`}>
          {item.status ? statusLabels[item.status] ?? item.status : 'Статус неизвестен'}
        </span>
        <span className="catalogue-card__version">{secondaryLabel ?? `Версия ${item.version}`}</span>
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

      {requiredCharacteristics.length > 0 && (
        <section className="catalogue-card__required" aria-label="Обязательные характеристики">
          <div className="catalogue-card__required-heading">
            <strong>Обязательные характеристики</strong>
            <span>{requiredCharacteristics.length}</span>
          </div>
          <dl className="catalogue-card__characteristics">
            {visibleRequired.map((characteristic) => (
              <div key={characteristic.id}>
                <dt>{characteristic.name ?? 'Без названия'}<span>обязательная</span></dt>
                <dd>
                  {characteristic.values.length > 0
                    ? characteristic.values.slice(0, 3).map((value, index) => (
                        <span key={`${value.value_code ?? 'value'}-${index}`}>{formatValue(value)}</span>
                      ))
                    : <span>Допустимые значения не указаны</span>}
                  {characteristic.values.length > 3 && <span>+{characteristic.values.length - 3}</span>}
                </dd>
              </div>
            ))}
          </dl>
          {requiredCharacteristics.length > visibleRequired.length && (
            <p className="catalogue-card__required-more">
              Ещё {requiredCharacteristics.length - visibleRequired.length} обязательных — в полной карточке
            </p>
          )}
        </section>
      )}

      <div className="catalogue-card__bottom">
        <span>{requiredCharacteristics.length} обязательных из {item.characteristics.length}</span>
        <a href={`#/catalogue/${encodeURIComponent(item.code)}`}>Подробнее <span aria-hidden="true">→</span></a>
      </div>
    </article>
  )
}
