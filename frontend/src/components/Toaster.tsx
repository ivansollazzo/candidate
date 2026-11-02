import { CircleAlert, CircleCheck, TriangleAlert, X } from "lucide-react"
import type { CSSProperties } from "react"
import { Link } from "react-router"

import { useT } from "@/lib/i18n"
import { dismissToast, TOAST_MS, useToasts, type Toast } from "@/lib/toast"
import { cn } from "@/lib/utils"

const TONES = {
  success: { icon: CircleCheck, badge: "bg-emerald-500/12 text-emerald-600 dark:text-emerald-400", bar: "bg-emerald-500" },
  warning: { icon: TriangleAlert, badge: "bg-amber-500/12 text-amber-600 dark:text-amber-400", bar: "bg-amber-500" },
  error: { icon: CircleAlert, badge: "bg-red-500/12 text-red-600 dark:text-red-400", bar: "bg-red-500" },
}

function ToastCard({ item }: { item: Toast }) {
  const t = useT()
  const tone = TONES[item.tone]
  const Icon = tone.icon
  const close = () => dismissToast(item.id)
  return (
    <div className="toast toast-in pointer-events-auto relative overflow-hidden rounded-xl border bg-background/95 shadow-lg ring-1 ring-black/5 backdrop-blur dark:ring-white/5">
      <div className="flex items-start gap-3 p-3.5 pr-10">
        <span className={cn("flex size-8 shrink-0 items-center justify-center rounded-full", tone.badge)}>
          <Icon className="size-4.5" />
        </span>
        <div className="min-w-0 flex-1 pt-0.5">
          <p className="text-sm font-medium leading-5">{item.title}</p>
          {item.description && <p className="truncate text-sm text-muted-foreground">{item.description}</p>}
          {item.to && (
            <Link to={item.to} onClick={close}
              className="mt-2 inline-flex h-7 items-center rounded-md border px-2.5 text-xs font-medium hover:bg-accent">
              {t("toast.open")}
            </Link>
          )}
        </div>
      </div>
      <button type="button" aria-label={t("common.close")} onClick={close}
        className="absolute right-2 top-2 rounded-md p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground">
        <X className="size-4" />
      </button>
      <div className={cn("toast-timer absolute inset-x-0 bottom-0 h-0.5 opacity-60", tone.bar)}
        style={{ "--toast-duration": `${TOAST_MS}ms` } as CSSProperties} onAnimationEnd={close} />
    </div>
  )
}

export function Toaster() {
  const toasts = useToasts()
  if (toasts.length === 0) return null
  return (
    <div role="status" aria-live="polite"
      className="pointer-events-none fixed bottom-4 right-4 z-40 flex w-96 max-w-[calc(100vw-2rem)] flex-col gap-2.5">
      {toasts.map((item) => <ToastCard key={item.id} item={item} />)}
    </div>
  )
}
