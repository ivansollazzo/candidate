import { X } from "lucide-react"
import { Link } from "react-router"

import { useT } from "@/lib/i18n"
import { dismissToast, useToasts } from "@/lib/toast"
import { cn } from "@/lib/utils"

export function Toaster() {
  const t = useT()
  const toasts = useToasts()
  if (toasts.length === 0) return null
  return (
    <div role="status" aria-live="polite" className="fixed bottom-4 right-4 z-40 flex w-80 max-w-[calc(100vw-2rem)] flex-col gap-2">
      {toasts.map((item) => (
        <div key={item.id} className={cn("flex items-start gap-2 rounded-lg border bg-background p-3 text-sm shadow-lg",
          item.tone === "error" ? "border-red-300 dark:border-red-900" : "border-emerald-300 dark:border-emerald-900")}>
          {item.to ? (
            <Link to={item.to} className="min-w-0 flex-1 hover:underline" onClick={() => dismissToast(item.id)}>{item.text}</Link>
          ) : (
            <span className="min-w-0 flex-1">{item.text}</span>
          )}
          <button type="button" aria-label={t("common.close")} className="text-muted-foreground hover:text-foreground"
            onClick={() => dismissToast(item.id)}>
            <X className="size-4" />
          </button>
        </div>
      ))}
    </div>
  )
}
