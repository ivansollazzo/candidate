import { Loader2, Save } from "lucide-react"

import { Button } from "@/components/ui/button"
import { useT } from "@/lib/i18n"

/** Bottom bar with the form actions. */
export function SaveBar({ message, saving, error, disabled, onCancel, onSave, saveLabel }: {
  message: string
  saving: boolean
  error?: string | null
  disabled?: boolean
  onCancel?: () => void
  onSave: () => void
  saveLabel?: string
}) {
  const t = useT()
  return (
    <div className="fixed inset-x-0 bottom-0 z-10 border-t bg-background/95 backdrop-blur">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-end gap-3 px-4 py-3">
        {error && <span className="text-sm text-red-600 dark:text-red-400">{error}</span>}
        <span className="text-sm text-muted-foreground">{message}</span>
        {onCancel && <Button variant="ghost" onClick={onCancel}>{t("common.cancel")}</Button>}
        <Button disabled={saving || disabled} onClick={onSave}>
          {saving ? <Loader2 className="animate-spin" /> : <Save />}{saveLabel ?? t("common.save")}
        </Button>
      </div>
    </div>
  )
}
