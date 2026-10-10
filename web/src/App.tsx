import { useEffect, useState } from 'react'
import Catalogue from './components/Catalogue'
import CatalogueItemRoute from './components/CatalogueItemRoute'
import CategoryFilters, { type Category } from './components/CategoryFilters'
import SearchBar from './components/SearchBar'
import ThemeSwitcher, { type ThemePreference } from './components/ThemeSwitcher'

const categoryByQueryValue: Record<string, Category> = {
  instruments: 'tools',
  clothes: 'clothing',
  furniture: 'furniture',
  tools: 'tools',
  clothing: 'clothing',
}

const queryValueByCategory: Record<Exclude<Category, 'all'>, string> = {
  tools: 'instruments',
  clothing: 'clothes',
  furniture: 'furniture',
}

function getCategoryFromUrl(): Category {
  const value = new URLSearchParams(window.location.search).get('category')
  return value ? categoryByQueryValue[value.toLowerCase()] ?? 'all' : 'all'
}

function getPageFromUrl(): number {
  const value = Number(new URLSearchParams(window.location.search).get('page'))
  return Number.isInteger(value) && value > 0 ? value : 1
}

function getInitialTheme(): ThemePreference {
  const savedTheme = localStorage.getItem('ktru-theme')
  if (savedTheme === 'light' || savedTheme === 'dark' || savedTheme === 'system') return savedTheme
  return 'system'
}

export default function App() {
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState<Category>(getCategoryFromUrl)
  const [page, setPage] = useState(getPageFromUrl)
  const [routeHash, setRouteHash] = useState(window.location.hash)
  const [themePreference, setThemePreference] = useState<ThemePreference>(getInitialTheme)
  const [systemTheme, setSystemTheme] = useState<'light' | 'dark'>(() =>
    window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light',
  )

  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
    const handleSystemThemeChange = (event: MediaQueryListEvent) => {
      setSystemTheme(event.matches ? 'dark' : 'light')
    }

    mediaQuery.addEventListener('change', handleSystemThemeChange)
    return () => mediaQuery.removeEventListener('change', handleSystemThemeChange)
  }, [])

  useEffect(() => {
    const resolvedTheme = themePreference === 'system' ? systemTheme : themePreference
    document.documentElement.dataset.theme = resolvedTheme
    localStorage.setItem('ktru-theme', themePreference)
    document.querySelector('meta[name="theme-color"]')?.setAttribute(
      'content',
      resolvedTheme === 'dark' ? '#111713' : '#f5f7f4',
    )
  }, [systemTheme, themePreference])

  useEffect(() => {
    const handleHashChange = () => setRouteHash(window.location.hash)
    const handlePopState = () => {
      setCategory(getCategoryFromUrl())
      setPage(getPageFromUrl())
    }
    window.addEventListener('hashchange', handleHashChange)
    window.addEventListener('popstate', handlePopState)
    return () => {
      window.removeEventListener('hashchange', handleHashChange)
      window.removeEventListener('popstate', handlePopState)
    }
  }, [])

  const handleSearch = () => {
    // Search results and API integration are introduced in later steps.
  }

  const handleCategoryChange = (nextCategory: Category) => {
    const url = new URL(window.location.href)

    if (nextCategory === 'all') {
      url.searchParams.delete('category')
    } else {
      url.searchParams.set('category', queryValueByCategory[nextCategory])
    }

    url.searchParams.delete('page')
    window.history.pushState({}, '', url)
    setCategory(nextCategory)
    setPage(1)
  }

  const handlePageChange = (nextPage: number) => {
    const url = new URL(window.location.href)
    if (nextPage <= 1) url.searchParams.delete('page')
    else url.searchParams.set('page', String(nextPage))
    window.history.pushState({}, '', url)
    setPage(Math.max(1, nextPage))
    document.getElementById('catalogue')?.scrollIntoView({ behavior: 'smooth' })
  }

  const selectedItemCode = routeHash.startsWith('#/catalogue/')
    ? decodeURIComponent(routeHash.slice('#/catalogue/'.length))
    : null

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
          <ThemeSwitcher
            value={themePreference}
            onChange={setThemePreference}
          />
        </div>
      </header>

      {selectedItemCode ? (
        <CatalogueItemRoute code={selectedItemCode} />
      ) : (
      <main className="page-main">
        <div className="container">
          <section className="hero" aria-labelledby="page-title">
            <p className="eyebrow">Умный поиск по каталогу</p>
            <h1 id="page-title">Найдите подходящую позицию КТРУ</h1>
            <p className="hero__description">
              Опишите нужный товар обычными словами — сервис поможет определить
              категорию и подобрать характеристики.
            </p>

            <SearchBar
              value={query}
              onChange={setQuery}
              onSubmit={handleSearch}
            />
          </section>

          <section className="catalogue-section" id="catalogue" aria-labelledby="catalogue-title">
            <div className="catalogue-section__heading">
              <div>
                <p className="eyebrow">Каталог КТРУ</p>
                <h2 id="catalogue-title">Позиции каталога</h2>
              </div>
              <p className="catalogue-section__description">
                Данные API · постраничная загрузка
              </p>
            </div>

            <CategoryFilters value={category} onChange={handleCategoryChange} />
            <Catalogue category={category} page={page} onPageChange={handlePageChange} />
          </section>
        </div>
      </main>
      )}
    </div>
  )
}
