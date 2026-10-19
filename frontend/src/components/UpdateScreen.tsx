import { Loader2 } from "lucide-react"

import { Logo } from "@/components/Logo"
import { useT } from "@/lib/i18n"
import { useUpdateProgress } from "@/lib/updates"

/** Covers the app while a new version is installed, then the page reloads by itself. */
export function UpdateScreen() {
  const t = useT()
  const { running, step } = useUpdateProgress()
  if (!running) return null
  return (
    <div role="alertdialog" aria-modal="true" aria-labelledby="update-title"
      className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-5 bg-background p-6 text-center">
      <Logo className="h-8" />
      <Loader2 className="size-8 animate-spin text-muted-foreground" />
      <div className="space-y-1">
        <h1 id="update-title" className="text-lg font-semibold">{t("update.title")}</h1>
        <p className="text-sm text-muted-foreground">{t(`update.step.${step}`)}</p>
      </div>
      <p className="max-w-sm text-xs text-muted-foreground">{t("update.hint")}</p>
    </div>
  )
}
