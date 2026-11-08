import { Loader2 } from "lucide-react"

import { useRestoring } from "@/features/backups/hooks"
import { Logo } from "@/shared/components/Logo"
import { useT } from "@/shared/lib/i18n"

/** Covers the app, for every user, while a backup is restored; the page reloads when it is done. */
export function RestoreScreen() {
  const t = useT()
  if (!useRestoring()) return null
  return (
    <div role="alertdialog" aria-modal="true" aria-labelledby="restore-title"
      className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-5 bg-background p-6 text-center">
      <Logo className="h-8" />
      <div className="max-w-sm space-y-3">
        <h1 id="restore-title" className="flex items-center justify-center gap-2 text-lg font-semibold">
          <Loader2 className="size-5 animate-spin" /> {t("restore.title")}
        </h1>
        <p className="text-sm text-muted-foreground">{t("restore.hint")}</p>
      </div>
    </div>
  )
}
