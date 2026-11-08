import { Loader2 } from "lucide-react"

import { useUpdateProgress } from "@/features/updates/hooks"
import { Logo } from "@/shared/components/Logo"
import { useT } from "@/shared/lib/i18n"

/** Thin bar under the header while the database is saved and the new version downloaded: the app stays usable. */
export function UpdateBanner() {
  const t = useT()
  const { running, blocking, step, progress } = useUpdateProgress()
  if (blocking || !running) return null
  return (
    <div className="border-b bg-secondary/60">
      <div className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-1.5 text-xs text-muted-foreground">
        <Loader2 className="size-3.5 shrink-0 animate-spin" />
        <span className="min-w-0 flex-1 truncate">
          {t("update.title")} · {t(`update.step.${step}`)}
        </span>
        <div className="hidden h-1.5 w-32 overflow-hidden rounded-full bg-background sm:block">
          <div className="h-full rounded-full bg-primary transition-[width] duration-700" style={{ width: `${progress}%` }} />
        </div>
        <span className="tabular-nums">{progress}%</span>
      </div>
    </div>
  )
}

/** Covers the app while the services are replaced by the new version, then the page reloads by itself. */
export function UpdateScreen() {
  const t = useT()
  const { blocking, step, progress } = useUpdateProgress()
  if (!blocking) return null
  return (
    <div role="alertdialog" aria-modal="true" aria-labelledby="update-title"
      className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-5 bg-background p-6 text-center">
      <Logo className="h-8" />
      <div className="w-full max-w-sm space-y-3">
        <h1 id="update-title" className="text-lg font-semibold">{t("update.title")}</h1>
        <div role="progressbar" aria-labelledby="update-title" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress}
          className="relative h-2 overflow-hidden rounded-full bg-secondary">
          <div className="h-full rounded-full bg-primary transition-[width] duration-700 ease-out" style={{ width: `${progress}%` }} />
          {/* Moving sheen: waiting for the new version to start brings no new progress */}
          <div className="absolute inset-y-0 w-1/3 animate-[update-sheen_1.6s_ease-in-out_infinite] motion-reduce:hidden bg-gradient-to-r from-transparent via-white/40 to-transparent" />
        </div>
        <p className="flex justify-between gap-3 text-sm text-muted-foreground">
          <span>{t(`update.step.${step}`)}</span>
          <span className="tabular-nums">{progress}%</span>
        </p>
      </div>
      <p className="max-w-sm text-xs text-muted-foreground">{t("update.hint")}</p>
    </div>
  )
}
