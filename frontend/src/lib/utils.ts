import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

import { dateLocale, type MessageKey, t } from "./i18n"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export const SALARY_PERIODS = ["annual", "monthly", "daily", "hourly"] as const
export const SALARY_BASES = ["gross", "net"] as const

/** "35.000 – 42.000 €", "annual", "gross" → "35.000 – 42.000 € · annua lorda" */
export function formatSalary(salary: string | null, period: string | null, basis: string | null) {
  if (!salary) return null
  const periodText = period && (SALARY_PERIODS as readonly string[]).includes(period) ? t(`salaryPeriod.${period}` as MessageKey) : ""
  const basisText = basis && (SALARY_BASES as readonly string[]).includes(basis) ? t(`salaryBasis.${basis}` as MessageKey) : ""
  const kind = periodText && basisText ? t("salary.kind", { period: periodText, basis: basisText }) : periodText || basisText
  return kind ? `${salary} · ${kind}` : salary
}

export function formatDate(value: string | null) {
  if (!value) return null
  return new Date(value).toLocaleDateString(dateLocale(), { day: "2-digit", month: "short", year: "numeric" })
}

/** Today's local date as "YYYY-MM-DD" */
export function today() {
  return isoDate(new Date())
}

export function isoDate(date: Date) {
  const pad = (n: number) => String(n).padStart(2, "0")
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

/** "2023-10" → "ott 2023" / "Oct 2023", "2023" → "2023"; other formats are returned unchanged. */
export function formatMonth(value: string | null | undefined) {
  if (!value) return null
  const m = /^(\d{4})(?:-(\d{1,2}))?$/.exec(value.trim())
  if (!m) return value
  const month = Number(m[2])
  if (!m[2] || month < 1 || month > 12) return m[1]
  return new Date(Number(m[1]), month - 1, 1).toLocaleDateString(dateLocale(), { month: "short", year: "numeric" })
}

export function formatPeriod(start?: string | null, end?: string | null, current?: boolean) {
  const from = formatMonth(start)
  const to = current ? t("date.present") : formatMonth(end)
  return [from, to].filter(Boolean).join(" – ")
}
