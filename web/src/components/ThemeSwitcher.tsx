import { TbMoon, TbSun, TbSunMoon } from 'react-icons/tb'

export type ThemePreference = 'light' | 'dark' | 'system'

type ThemeSwitcherProps = {
  value: ThemePreference
  onChange: (theme: ThemePreference) => void
}

const themeLabels: Record<ThemePreference, string> = {
  light: 'светлая',
  dark: 'тёмная',
  system: 'системная',
}

const nextTheme: Record<ThemePreference, ThemePreference> = {
  light: 'dark',
  dark: 'system',
  system: 'light',
}

export default function ThemeSwitcher({ value, onChange }: ThemeSwitcherProps) {
  const next = nextTheme[value]
  const ThemeIcon = value === 'light' ? TbSun : value === 'dark' ? TbMoon : TbSunMoon

  return (
    <button
      className="theme-switcher"
      type="button"
      onClick={() => onChange(next)}
      aria-label={`Текущая тема: ${themeLabels[value]}. Переключить на ${themeLabels[next]}`}
      title={`Тема: ${themeLabels[value]}. Следующая: ${themeLabels[next]}`}
    >
      <ThemeIcon aria-hidden="true" />
    </button>
  )
}
