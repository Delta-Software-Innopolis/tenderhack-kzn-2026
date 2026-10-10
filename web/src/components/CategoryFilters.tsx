export type Category = 'all' | 'tools' | 'furniture' | 'clothing'

type CategoryFiltersProps = {
  value: Category
  onChange: (category: Category) => void
}

const categories: Array<{ value: Category; label: string }> = [
  { value: 'all', label: 'Все' },
  { value: 'tools', label: 'Инструменты' },
  { value: 'furniture', label: 'Мебель' },
  { value: 'clothing', label: 'Одежда' },
]

export default function CategoryFilters({
  value,
  onChange,
}: CategoryFiltersProps) {
  return (
    <div className="category-filters" aria-label="Фильтр по категории">
      {categories.map((category) => (
        <button
          className="category-filter"
          type="button"
          key={category.value}
          aria-pressed={value === category.value}
          onClick={() => onChange(category.value)}
        >
          {category.label}
        </button>
      ))}
    </div>
  )
}
