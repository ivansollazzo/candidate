import { Select } from "@/components/ui/input"
import { LOCALES, type Locale, useT } from "@/lib/i18n"

/** Language picker shared by login, settings and user creation. */
export function LanguageSelect({ value, onChange, className, disabled }: {
  value: Locale | undefined
  onChange: (locale: Locale) => void
  className?: string
  disabled?: boolean
}) {
  const t = useT()
  return (
    <Select className={className} aria-label={t("settings.language")} value={value} disabled={disabled}
      onChange={(e) => onChange(e.target.value as Locale)}>
      {LOCALES.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}
    </Select>
  )
}
