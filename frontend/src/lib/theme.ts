import { useEffect } from "react"

import type { Theme } from "./api"
import { useCurrentUser } from "./auth"

export const THEMES: Theme[] = ["light", "dark", "system"]

// Same key read by the script in index.html, which applies the theme before first paint
const STORAGE_KEY = "candidate-theme"

const dark = window.matchMedia("(prefers-color-scheme: dark)")

function apply(theme: Theme) {
  document.documentElement.classList.toggle("dark", theme === "dark" || (theme === "system" && dark.matches))
}

/**
 * Applies the user's theme and, with "system", follows OS changes.
 * Before login the last user's theme stays, as applied by index.html.
 */
export function ThemeSync() {
  const theme = useCurrentUser()?.theme
  useEffect(() => {
    if (!theme) return
    apply(theme)
    try {
      localStorage.setItem(STORAGE_KEY, theme)
    } catch {
      /* storage unavailable: the theme still comes from the user */
    }
    if (theme !== "system") return
    const follow = () => apply(theme)
    dark.addEventListener("change", follow)
    return () => dark.removeEventListener("change", follow)
  }, [theme])
  return null
}
