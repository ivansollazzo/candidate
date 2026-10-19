import { Logo } from "@/components/Logo"
import { useT } from "@/lib/i18n"
import { useUpdateProgress } from "@/lib/updates"

/** Covers the app while a new version is installed, then the page reloads by itself. */
export function UpdateScreen() {
  const t = useT()
  const { running, step, progress } = useUpdateProgress()
  if (!running) return null
  return (
    <div role="alertdialog" aria-modal="true" aria-labelledby="update-title"
      className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-5 bg-background p-6 text-center">
      <Logo className="h-8" />
      <div className="w-full max-w-sm space-y-3">
        <h1 id="update-title" className="text-lg font-semibold">{t("update.title")}</h1>
        <div role="progressbar" aria-labelledby="update-title" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress}
          className="relative h-2 overflow-hidden rounded-full bg-secondary">
          <div className="h-full rounded-full bg-primary transition-[width] duration-700 ease-out" style={{ width: `${progress}%` }} />
          {/* Moving sheen: steps such as installing dependencies take minutes without new progress */}
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
