export default function App() {
  return (
    <div className="app-shell">
      <header className="site-header">
        <div className="container site-header__inner">
          <a className="brand" href="/" aria-label="КТРУ — главная">
            <span className="brand__mark" aria-hidden="true">К</span>
            <span className="brand__name">КТРУ</span>
          </a>
          <span className="site-header__descriptor">
            Каталог товаров, работ и услуг
          </span>
        </div>
      </header>

      <main className="page-main">
        <div className="container">
          <section className="hero" aria-labelledby="page-title">
            <p className="eyebrow">Умный поиск по каталогу</p>
            <h1 id="page-title">Найдите подходящую позицию КТРУ</h1>
            <p className="hero__description">
              Опишите нужный товар обычными словами — сервис поможет определить
              категорию и подобрать характеристики.
            </p>
          </section>
        </div>
      </main>
    </div>
  )
}
