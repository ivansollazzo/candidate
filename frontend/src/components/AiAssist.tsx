import { FileText, FileUp, Link2, Loader2, type LucideIcon, Save, Sparkles } from "lucide-react"
import { type ReactNode, useState } from "react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input, Textarea } from "@/components/ui/input"
import { useAiStatus } from "@/lib/ai"
import { type AITask, api, type Application, type JobSource } from "@/lib/api"
import { type MessageKey, useT } from "@/lib/i18n"
import { cn } from "@/lib/utils"

/**
 * Shared by applications and profile: the AI fills the form, which the user then reviews and saves.
 * Hidden when AI features are disabled in settings.
 */
export function AiAssist({ hint, running, error, canRun, onRun, children }: {
  hint: string
  running: boolean
  error: string | null
  canRun: boolean
  onRun: () => void
  children?: ReactNode
}) {
  const t = useT()
  const ai = useAiStatus()
  if (!ai.enabled) return null
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><Sparkles className="size-4" />{t("ai.title")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-muted-foreground">{hint}</p>
        {children}
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="outline" disabled={!ai.ready || !canRun || running} onClick={onRun}>
            {running ? <Loader2 className="animate-spin" /> : <Sparkles />}
            {running ? t("ai.running") : t("ai.run")}
          </Button>
          {running && (
            <span className="text-sm text-muted-foreground">{t("ai.wait")}</span>
          )}
          {!ai.ready && <span className="text-sm text-muted-foreground">{ai.reason}</span>}
        </div>
        {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
      </CardContent>
    </Card>
  )
}

type Tab = "saved" | "text" | "link" | "file"

const TABS: { value: Tab; label: MessageKey; icon: LucideIcon }[] = [
  { value: "saved", label: "source.saved", icon: Save },
  { value: "text", label: "source.text", icon: FileText },
  { value: "link", label: "source.link", icon: Link2 },
  { value: "file", label: "source.file", icon: FileUp },
]

const isUrl = (value: string) => /^https?:\/\/\S+\.\S+/.test(value.trim())

/** Job posting source: pasted text, link, file or (in the detail view) the saved one. */
export function useJobSource(savedApplicationId?: number) {
  const t = useT()
  const [tab, setTab] = useState<Tab>(savedApplicationId != null ? "saved" : "text")
  const [text, setText] = useState("")
  const [url, setUrl] = useState("")
  const [file, setFile] = useState<File | null>(null)

  const source: JobSource | null =
    tab === "saved" && savedApplicationId != null ? { application_id: savedApplicationId }
      : tab === "text" && text.trim().length >= 20 ? { text }
        : tab === "link" && isUrl(url) ? { url: url.trim() }
          : tab === "file" && file ? { file }
            : null

  const input = (
    <div className="space-y-3">
      <div className="inline-flex flex-wrap rounded-md border p-0.5" role="tablist">
        {TABS.filter((tab) => tab.value !== "saved" || savedApplicationId != null).map(({ value, label, icon: Icon }) => (
          <button key={value} type="button" role="tab" aria-selected={tab === value} onClick={() => setTab(value)}
            className={cn(
              "flex items-center gap-1.5 rounded px-3 py-1 text-sm text-muted-foreground hover:text-foreground",
              tab === value && "bg-secondary text-foreground",
            )}>
            <Icon className="size-4" />{t(label)}
          </button>
        ))}
      </div>
      {tab === "saved" && (
        <p className="text-sm text-muted-foreground">{t("source.savedHint")}</p>
      )}
      {tab === "text" && (
        <Textarea className="min-h-40 font-mono text-xs" placeholder={t("source.textPlaceholder")}
          value={text} onChange={(e) => setText(e.target.value)} />
      )}
      {tab === "link" && (
        <div className="space-y-1">
          <Input type="url" placeholder="https://…" value={url} onChange={(e) => setUrl(e.target.value)} />
          <p className="text-xs text-muted-foreground">{t("source.linkHint")}</p>
        </div>
      )}
      {tab === "file" && (
        <div className="flex flex-wrap items-center gap-3">
          <label className="inline-flex cursor-pointer items-center gap-2 rounded-md border px-3 py-1.5 text-sm hover:bg-accent">
            <FileUp className="size-4" />
            {file ? file.name : t("source.chooseFile")}
            <input type="file" className="hidden" accept=".pdf,.docx,.txt,.md"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </label>
          {file && <Button variant="ghost" size="sm" onClick={() => setFile(null)}>{t("source.removeFile")}</Button>}
        </div>
      )}
    </div>
  )
  return { source, input, url: tab === "link" && isUrl(url) ? url.trim() : null }
}

/** AI fill from a job posting, for new and existing applications. */
export function JobPostingAssist({ hint, job, fill }: {
  hint: string
  job: ReturnType<typeof useJobSource>
  fill: { run: (fn: () => Promise<AITask<Partial<Application>>>) => void; running: boolean; error: string | null }
}) {
  return (
    <AiAssist hint={hint} running={fill.running} error={fill.error} canRun={job.source != null}
      onRun={() => job.source && fill.run(() => api.fillJobPosting(job.source!))}>
      {job.input}
    </AiAssist>
  )
}
