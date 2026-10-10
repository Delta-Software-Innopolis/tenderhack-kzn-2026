import type { FormEvent } from 'react'

type SearchBarProps = {
  value: string
  onChange: (value: string) => void
  onSubmit: () => void
  isLoading?: boolean
}

export default function SearchBar({
  value,
  onChange,
  onSubmit,
  isLoading = false,
}: SearchBarProps) {
  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    onSubmit()
  }

  return (
    <form className="search-form" role="search" onSubmit={handleSubmit}>
      <label className="search-form__label" htmlFor="catalogue-search">
        Что вы ищете?
      </label>

      <div className="search-form__control">
        <span className="search-form__leading-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none">
            <circle cx="11" cy="11" r="6.5" />
            <path d="m16 16 4 4" />
          </svg>
        </span>

        <input
          id="catalogue-search"
          name="query"
          type="search"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder="Например, молоток слесарный 20 см"
          autoComplete="off"
          enterKeyHint="search"
        />

        <button
          className="search-form__submit"
          type="submit"
          aria-label="Найти в каталоге"
          disabled={!value.trim() || isLoading}
        >
          {isLoading ? (
            <span className="search-form__spinner" aria-hidden="true" />
          ) : (
            <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <circle cx="10.75" cy="10.75" r="6.75" />
              <path d="m16 16 4.25 4.25" />
            </svg>
          )}
        </button>
      </div>

      <p className="search-form__hint">
        Укажите назначение, тип, размер или другие важные характеристики
      </p>
    </form>
  )
}
