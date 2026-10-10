import { useEffect, useState } from 'react'
import Catalogue from './components/Catalogue'
import CatalogueItemRoute from './components/CatalogueItemRoute'
import { type Category } from './components/CategoryFilters'
import SearchBar from './components/SearchBar'
import SearchResults from './components/SearchResults'
import ThemeSwitcher, { type ThemePreference } from './components/ThemeSwitcher'
import { useSearch } from './hooks/useSearch'

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
  const search = useSearch()

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
    const normalizedQuery = query.trim()
    if (!normalizedQuery) return
    search.mutate(normalizedQuery, {
      onSuccess: () => {
        window.setTimeout(() => {
          document.getElementById('search-form')?.scrollIntoView({ behavior: 'smooth' })
        }, 0)
      },
    })
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
            <div className="hero__intro">
              <div className="hero__copy">
                <p className="eyebrow">Умный поиск по каталогу</p>
                <h1 id="page-title">Найдите подходящую позицию КТРУ</h1>
                <p className="hero__description">
                  Опишите нужный товар обычными словами — сервис поможет определить
                  категорию и подобрать характеристики.
                </p>
              </div>
              <img
                className="hero__mascot"
                src="/rembo-slim.png"
                alt="Робот-помощник Рэмбо"
              />
            </div>

            <SearchBar
              value={query}
              onChange={setQuery}
              onSubmit={handleSearch}
              isLoading={search.isPending}
            />
          </section>

          {search.isError && (
            <div className="search-error" role="alert">
              <strong>Не удалось выполнить поиск.</strong>
              <span>{search.error.message}</span>
            </div>
          )}

          {search.data && <SearchResults result={search.data} />}

          <section className="catalogue-section" id="catalogue" aria-labelledby="catalogue-title">
            <div className="catalogue-section__heading">
              <div>
                {/* <p className="eyebrow"></p> */}
                <h2 id="catalogue-title">Каталог КТРУ</h2>
              </div>
              <p className="catalogue-section__description">
                Данные API · постраничная загрузка
              </p>
            </div>

            <Catalogue
              category={category}
              page={page}
              onCategoryChange={handleCategoryChange}
              onPageChange={handlePageChange}
            />
          </section>
        </div>
      </main>
      )}
      <footer className="site-footer">
        <div className="container site-footer__inner">
          <span>Команда <strong>SL</strong></span>
          <a
            href="https://github.com/Delta-Software-Innopolis/tenderhack-kzn-2026"
            target="_blank"
            rel="noreferrer"
          >
            <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <path d="M12 2a10 10 0 0 0-3.16 19.49c.5.09.68-.22.68-.48v-1.87c-2.78.6-3.37-1.18-3.37-1.18-.45-1.16-1.11-1.47-1.11-1.47-.91-.62.07-.61.07-.61 1 .07 1.53 1.03 1.53 1.03.9 1.53 2.35 1.09 2.92.83.09-.65.35-1.09.64-1.34-2.22-.25-4.55-1.11-4.55-4.94 0-1.09.39-1.98 1.03-2.68-.1-.25-.45-1.27.1-2.64 0 0 .84-.27 2.75 1.02A9.6 9.6 0 0 1 12 6.82a9.6 9.6 0 0 1 2.5.34c1.91-1.29 2.75-1.02 2.75-1.02.55 1.37.2 2.39.1 2.64.64.7 1.03 1.59 1.03 2.68 0 3.84-2.34 4.68-4.56 4.93.36.31.68.92.68 1.85V21c0 .27.18.58.69.48A10 10 0 0 0 12 2Z" />
            </svg>
            GitHub
          </a>
        </div>
      </footer>
    </div>
  )
}
