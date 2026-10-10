import type { CatalogueItem, KtruCharacteristicValue } from '../types/ktru'

type CatalogueItemPageProps = { item: CatalogueItem }

const notation: Record<string, string> = {
  greater: '>', greaterOrEqual: '≥', less: '<', lessOrEqual: '≤',
}

function formatValue(value: KtruCharacteristicValue): string {
  const unit = value.okei_name ? ` ${value.okei_name}` : ''
  if (value.quality_description) return value.quality_description
  if (value.concrete_value !== null) return `${value.concrete_value}${unit}`

  const parts = []
  if (value.min_value !== null) parts.push(`${notation[value.min_notation ?? ''] ?? ''} ${value.min_value}`.trim())
  if (value.max_value !== null) parts.push(`${notation[value.max_notation ?? ''] ?? ''} ${value.max_value}`.trim())
  return parts.length ? `${parts.join(' · ')}${unit}` : 'Значение не указано'
}

function formatDate(value: string | null) {
  if (!value) return 'Не указана'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('ru-RU').format(date)
}

export default function CatalogueItemPage({ item }: CatalogueItemPageProps) {
  return (
    <main className="item-page">
      <div className="container">
        <a className="item-page__back" href="#catalogue">← Вернуться к каталогу</a>
        <header className="item-page__header">
          <div><p className="eyebrow">Позиция КТРУ</p><h1>{item.name ?? 'Без наименования'}</h1></div>
          <span className="item-page__code">{item.code}</span>
        </header>

        <section className="item-summary" aria-label="Основные сведения">
          <div><span>ОКПД-2</span><strong>{item.okpd2_code ?? 'Не указан'}</strong><p>{item.okpd2_name}</p></div>
          <div><span>Статус</span><strong>{item.status ?? 'Не указан'}</strong><p>Версия {item.version}</p></div>
          <div><span>Начало применения</span><strong>{formatDate(item.date_start)}</strong><p>Опубликовано: {formatDate(item.publish_date)}</p></div>
          <div><span>Тип позиции</span><strong>{item.is_template === 1 ? 'Шаблон' : 'Обычная позиция'}</strong></div>
        </section>

        {item.rubrics.length > 0 && (
          <section className="item-rubrics" aria-label="Рубрики КТРУ">
            <span>Рубрики</span>
            {item.rubrics.map((rubric, index) => (
              <strong key={`${rubric.code ?? 'rubric'}-${index}`}>{rubric.code ? `${rubric.code} · ` : ''}{rubric.name ?? 'Без названия'}</strong>
            ))}
          </section>
        )}

        <section className="item-characteristics" aria-labelledby="characteristics-title">
          <div className="item-characteristics__heading">
            <div><p className="eyebrow">Параметры позиции</p><h2 id="characteristics-title">Характеристики КТРУ</h2></div>
            <span>{item.characteristics.length}</span>
          </div>
          <div className="characteristics-table">
            {item.characteristics.map((characteristic) => (
              <div className="characteristic-row" key={characteristic.id}>
                <div className="characteristic-row__name">
                  <strong>{characteristic.name ?? 'Без названия'}</strong>
                  {characteristic.is_required === 1 && <span>Обязательная</span>}
                </div>
                <div className="characteristic-row__values">
                  {characteristic.values.length > 0
                    ? characteristic.values.map((value, index) => <span key={`${value.value_code ?? 'value'}-${index}`}>{formatValue(value)}</span>)
                    : <span>Допустимые значения не указаны</span>}
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </main>
  )
}
