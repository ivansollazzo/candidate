import { useQueryClient } from "@tanstack/react-query"
import { createContext, type ReactNode, useContext, useEffect, useRef, useState } from "react"

import type { MessageKey, Messages } from "@/shared/lib/locales/types"

export type Locale = "it" | "en" | "es" | "fr" | "de"

export const LOCALES: { value: Locale; label: string }[] = [
  { value: "it", label: "Italiano" },
  { value: "en", label: "English" },
  { value: "es", label: "Español" },
  { value: "fr", label: "Français" },
  { value: "de", label: "Deutsch" },
]

export type { MessageKey }

// Each language is a separate chunk, downloaded only when used
const LOADERS: Record<Locale, () => Promise<{ default: Messages }>> = {
  it: () => import("@/shared/lib/locales/it"),
  en: () => import("@/shared/lib/locales/en"),
  es: () => import("@/shared/lib/locales/es"),
  fr: () => import("@/shared/lib/locales/fr"),
  de: () => import("@/shared/lib/locales/de"),
}
const loaded: Partial<Record<Locale, Messages>> = {}

async function loadLocale(value: Locale) {
  loaded[value] ??= (await LOADERS[value]()).default
}

const isLocale = (value: string | null): value is Locale => LOCALES.some((l) => l.value === value)

// Current language, also read outside components (backend requests, date formatting)
let locale: Locale = "it"

export const getLocale = () => locale
export const dateLocale = () => (locale === "it" ? "it-IT" : "en-GB")

/** An ISO timestamp as a localized date and time, "—" when missing */
export const formatDateTime = (value: string | null) =>
  value ? new Date(value).toLocaleString(dateLocale(), { dateStyle: "medium", timeStyle: "short" }) : "—"

export function t(key: MessageKey, values?: Record<string, string | number>) {
  let text = loaded[locale]![key]
  for (const [name, value] of Object.entries(values ?? {})) text = text.replaceAll(`{${name}}`, String(value))
  return text
}

const LocaleContext = createContext<Locale>(locale)
const GuestLocaleContext = createContext<(locale: Locale) => void>(() => {})

// Language chosen before login (or the last user's), for the login screen
const STORAGE_KEY = "candidate-language"

function storedLocale(): Locale {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    if (isLocale(value)) return value
  } catch {
    /* storage unavailable */
  }
  // First run: the browser's language when supported
  const browser = navigator.language.slice(0, 2).toLowerCase()
  return isLocale(browser) ? browser : "en"
}

/** Follows the signed-in user's language (userLocale, known once loading is false) and re-renders the UI when it
changes. */
export function I18nProvider({ userLocale, loading, children }: {
  userLocale?: Locale | null
  loading: boolean
  children: ReactNode
}) {
  const queryClient = useQueryClient()
  const [guest, setGuest] = useState(storedLocale)
  const wanted = userLocale ?? guest
  const [ready, setReady] = useState<Locale | null>(null)
  // The previous language stays on screen while the new one downloads
  const current = loaded[wanted] ? wanted : ready
  if (current) locale = current // before the children, which read it while rendering
  const previous = useRef(current)

  useEffect(() => {
    let active = true
    loadLocale(wanted).then(() => active && setReady(wanted))
    return () => {
      active = false
    }
  }, [wanted])

  useEffect(() => {
    if (!current) return
    document.documentElement.lang = current
    try {
      localStorage.setItem(STORAGE_KEY, current)
    } catch {
      /* storage unavailable */
    }
    if (previous.current === current) return
    const first = previous.current === null
    previous.current = current
    // Backend messages and notes depend on the language
    if (!first) queryClient.invalidateQueries({ predicate: (q) => q.queryKey[0] !== "me" })
  }, [current, queryClient])

  if (loading || !current) return null
  return (
    <GuestLocaleContext.Provider value={setGuest}>
      <LocaleContext.Provider value={current}>{children}</LocaleContext.Provider>
    </GuestLocaleContext.Provider>
  )
}

/** Changes the language when nobody is logged in (login and first run). */
export const useSetGuestLocale = () => useContext(GuestLocaleContext)

/** `t` for components: re-renders them when the language changes. */
export function useT() {
  useContext(LocaleContext)
  return t
}
