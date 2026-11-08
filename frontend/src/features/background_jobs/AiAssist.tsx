import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Clock, FileText, FileUp, Link2, Loader2, type LucideIcon, RotateCcw, Save, Sparkles, X } from "lucide-react"
import { type ReactNode, useState } from "react"

import type { JobSource } from "@/features/applications/api"
import type { Job } from "@/features/background_jobs/api"
import { jobState, useJobActions } from "@/features/background_jobs/hooks"
import { useAiStatus } from "@/features/settings/ai"
import { ErrorText } from "@/shared/components/ErrorText"
import { isWorking } from "@/shared/lib/http"
import { type MessageKey, useT } from "@/shared/lib/i18n"
import { cn } from "@/shared/lib/utils"
import { Button } from "@/shared/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card"
import { Input, Textarea } from "@/shared/ui/input"

/** Labels of the fields the AI can propose, for applications and the profile */
const FIELD_LABELS: Record<string, MessageKey> = {
  title: "field.title",
  company: "field.company",
  location: "field.location",
  work_mode: "field.workMode",
  contract_type: "field.contract",
  seniority: "field.seniority",
  salary: "field.salary",
  salary_period: "field.salaryPeriod",
  salary_basis: "field.salaryBasis",
  experience_years_min: "field.experienceYears",
  education_required: "field.education",
  source_url: "field.sourceUrl",
  requirements: "application.requirements",
  nice_to_have: "application.niceToHave",
  responsibilities: "application.responsibilities",
  benefits: "application.benefits",
  full_name: "profile.fullName",
  headline: "profile.headline",
  email: "profile.email",
  phone: "profile.phone",
  years_of_experience: "profile.years",
  summary: "profile.summary",
  links: "profile.links",
  experiences: "profile.experiences",
  education: "profile.education",
  projects: "profile.projects",
  certifications: "profile.certifications",
}

function fieldLabel(field: string, kind: Job["kind"]) {
  // Same field names with different labels on applications and the profile
  if (field === "skills") return kind === "profile" ? "profile.skills" : "application.skills"
  if (field === "languages") return kind === "profile" ? "profile.languages" : "application.languages"
  if (field === "location" && kind === "profile") return "profile.city"
  return FIELD_LABELS[field]
}

/** Short text for a proposed value: lists show their names */
function preview(value: unknown): string {
  if (Array.isArray(value)) {
    return value.map((item) => (typeof item === "object" && item
      ? String(Object.values(item as Record<string, unknown>).find((v) => typeof v === "string") ?? "")
      : String(item))).filter(Boolean).join(", ")
  }
  return String(value ?? "")
}

/** Values found by the AI for fields that were already filled: applied only if the user confirms. */
export function ProposalCard({ job }: { job: Job }) {
  const t = useT()
  const { apply, cancel } = useJobActions()
  if (job.status !== "done" || !job.proposal) return null
  return (
    <Card className="border-amber-300 dark:border-amber-900">
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><Sparkles className="size-4" />{t("proposal.title")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p className="text-muted-foreground">{t("proposal.hint")}</p>
        <dl className="space-y-1.5">
          {Object.entries(job.proposal).map(([field, value]) => {
            const label = fieldLabel(field, job.kind)
            return (
              <div key={field} className="grid gap-x-3 sm:grid-cols-[12rem_1fr]">
                <dt className="font-medium">{label ? t(label) : field}</dt>
                <dd className="line-clamp-2 text-muted-foreground">{preview(value)}</dd>
              </div>
            )
          })}
        </dl>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" disabled={apply.isPending || cancel.isPending} onClick={() => apply.mutate(job)}>
            {t("proposal.apply")}
          </Button>
          <Button size="sm" variant="outline" disabled={apply.isPending || cancel.isPending} onClick={() => cancel.mutate(job)}>
            {t("proposal.ignore")}
          </Button>
        </div>
        <ErrorText error={apply.error ?? cancel.error} />
      </CardContent>
    </Card>
  )
}

/** Where the job of a card stands: waiting or running with its X, or failed with retry. */
function JobProgress({ job }: { job: Job | undefined }) {
  const t = useT()
  const { cancel, retry } = useJobActions()
  if (!job || !(isWorking(job.status) || job.status === "failed")) return null
  const onCancel = () => {
    if (job.new_application && !confirm(t("jobs.confirmCancelNew"))) return
    cancel.mutate(job)
  }
  return (
    <div className="space-y-1">
      {isWorking(job.status) ? (
        <p className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          {job.status === "running" ? <Loader2 className="size-4 animate-spin" /> : <Clock className="size-4" />}
          {jobState(job)}
          <span className="hidden sm:inline">· {t("jobs.leaveHint")}</span>
          <Button variant="ghost" size="sm" className="ml-auto" disabled={cancel.isPending} onClick={onCancel}>
            <X />{t("jobs.cancel")}
          </Button>
        </p>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          <ErrorText className="flex-1" error={`${t("jobs.failed")}: ${job.error ?? ""}`} />
          <Button variant="outline" size="sm" disabled={retry.isPending} onClick={() => retry.mutate(job)}>
            <RotateCcw />{t("jobs.retry")}
          </Button>
          <Button variant="ghost" size="sm" disabled={cancel.isPending} onClick={() => cancel.mutate(job)}>
            {t("jobs.dismiss")}
          </Button>
        </div>
      )}
      <ErrorText error={cancel.error ?? retry.error} />
    </div>
  )
}

/**
 * Shared by applications and profile: the AI works in the background, so the user can leave the page.
 * Hidden when AI features are disabled in settings.
 */
export function AiAssist({ hint, runLabel, job, canRun, onRun, children }: {
  hint: string
  runLabel: string
  /** Latest job of this card, if any */
  job: Job | undefined
  canRun: boolean
  onRun: () => Promise<unknown>
  children?: ReactNode
}) {
  const t = useT()
  const ai = useAiStatus()
  const queryClient = useQueryClient()
  const start = useMutation({
    mutationFn: onRun,
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["jobs"] }),
  })
  if (!ai.enabled) return null
  const busy = start.isPending || (job != null && isWorking(job.status))
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><Sparkles className="size-4" />{t("ai.title")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-muted-foreground">{hint}</p>
        {children}
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="outline" disabled={!canRun || busy} onClick={() => start.mutate()}>
            {start.isPending ? <Loader2 className="animate-spin" /> : <Sparkles />}
            {runLabel}
          </Button>
          {!ai.ready && <span className="text-sm text-muted-foreground">{t("jobs.modelNotReady", { reason: ai.reason ?? "" })}</span>}
        </div>
        <JobProgress job={job} />
        <ErrorText error={start.error} />
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

/**
 * Job posting source: pasted text, link, file or (in the detail view) the saved one.
 * `source` is undefined for the saved posting and null while nothing valid has been given.
 */
export function useJobSource(hasSaved = false) {
  const t = useT()
  const [tab, setTab] = useState<Tab>(hasSaved ? "saved" : "text")
  const [text, setText] = useState("")
  const [url, setUrl] = useState("")
  const [file, setFile] = useState<File | null>(null)

  const source: JobSource | undefined | null =
    tab === "saved" && hasSaved ? undefined
      : tab === "text" && text.trim().length >= 20 ? { text }
        : tab === "link" && isUrl(url) ? { url: url.trim() }
          : tab === "file" && file ? { file }
            : null
  const reset = () => {
    setText("")
    setUrl("")
    setFile(null)
  }

  const input = (
    <div className="space-y-3">
      <div className="inline-flex flex-wrap rounded-md border p-0.5" role="tablist">
        {TABS.filter((tab) => tab.value !== "saved" || hasSaved).map(({ value, label, icon: Icon }) => (
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
  return { source, input, reset }
}
