import type { CatalogueItem } from '../types/ktru'

type CatalogueItemPageProps = {
  item: CatalogueItem
}

export default function CatalogueItemPage({ item }: CatalogueItemPageProps) {
  return (
    <main className="item-page">
      <div className="container">
        <a className="item-page__back" href="#catalogue">← Вернуться к каталогу</a>

        <header className="item-page__header">
          <div>
            <p className="eyebrow">Позиция КТРУ</p>
            <h1>{item.name}</h1>
          </div>
          <span className="item-page__code">{item.code}</span>
        </header>

        <section className="item-summary" aria-label="Основные сведения">
          <div><span>ОКПД-2</span><strong>{item.okpd2.code}</strong><p>{item.okpd2.name}</p></div>
          <div><span>Единица измерения</span><strong>{item.unit.name} ({item.unit.symbol})</strong></div>
          <div><span>Тип позиции</span><strong>{item.positionType === 'non-aggregated' ? 'Неукрупнённая' : 'Укрупнённая'}</strong></div>
          <div><span>Доп. характеристики</span><strong>{item.additionalCharacteristicsAllowed ? 'Разрешены' : 'Не разрешены'}</strong></div>
        </section>

        <section className="item-characteristics" aria-labelledby="characteristics-title">
          <div className="item-characteristics__heading">
            <div>
              <p className="eyebrow">Параметры позиции</p>
              <h2 id="characteristics-title">Характеристики КТРУ</h2>
            </div>
            <span>{item.characteristics.length}</span>
          </div>

          <div className="characteristics-table">
            {item.characteristics.map((characteristic) => (
              <div className="characteristic-row" key={characteristic.name}>
                <div className="characteristic-row__name">
                  <strong>{characteristic.name}</strong>
                  {characteristic.required && <span>Обязательная</span>}
                </div>
                <div className="characteristic-row__values">
                  {characteristic.allowedValues.map((value) => (
                    <span className={value === characteristic.matchedValue ? 'is-matched' : undefined} key={String(value)}>
                      {value}{characteristic.unit ? ` ${characteristic.unit.symbol}` : ''}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </main>
  )
}
