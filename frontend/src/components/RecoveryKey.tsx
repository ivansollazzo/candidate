import { Check, Copy, Download, KeyRound } from "lucide-react"
import { useState } from "react"

import { Button } from "@/components/ui/button"
import { useT } from "@/lib/i18n"

function download(username: string, key: string, text: string) {
  const blob = new Blob([`${text}\n\n${username}\n${key}\n`], { type: "text/plain" })
  const link = document.createElement("a")
  link.href = URL.createObjectURL(blob)
  link.download = `candidate-${username}-recovery-key.txt`
  link.click()
  URL.revokeObjectURL(link.href)
}

/**
 * Freshly generated recovery key: shown only once, so it must be downloaded or copied.
 * The `onDone` action appears after the user confirms it was saved.
 */
export function RecoveryKey({ username, value, onDone, doneLabel, forOther }: {
  username: string
  value: string
  onDone: () => void
  doneLabel: string
  /** The key belongs to another user (created by the admin) */
  forOther?: boolean
}) {
  const t = useT()
  const [saved, setSaved] = useState(false)
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
    } catch {
      /* clipboard unavailable: download still works */
    }
  }

  return (
    <div className="space-y-3 rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm dark:border-amber-700 dark:bg-amber-950/40">
      <p className="flex items-center gap-2 font-medium text-amber-900 dark:text-amber-200">
        <KeyRound className="size-4" />{t("recovery.title")}
      </p>
      <p className="text-amber-900 dark:text-amber-200">{t(forOther ? "recovery.warningOther" : "recovery.warning")}</p>
      <p className="rounded-md border bg-card px-3 py-2 text-center font-mono text-base tracking-wider select-all">{value}</p>
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="outline" size="sm" onClick={() => download(username, value, t("recovery.fileText"))}>
          <Download />{t("recovery.download")}
        </Button>
        <Button type="button" variant="outline" size="sm" onClick={copy}>
          {copied ? <Check /> : <Copy />}{t(copied ? "recovery.copied" : "recovery.copy")}
        </Button>
      </div>
      <label className="flex items-center gap-2">
        <input type="checkbox" checked={saved} onChange={(e) => setSaved(e.target.checked)} />
        {t("recovery.confirm")}
      </label>
      <Button type="button" disabled={!saved} onClick={onDone}>{doneLabel}</Button>
    </div>
  )
}
