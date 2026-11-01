import { CircleAlert, CircleCheck, Clock, Download, ListChecks, Loader2, X } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { Link } from "react-router"

import { ErrorText } from "@/components/ErrorText"
import { Button } from "@/components/ui/button"
import { isWorking, type Job } from "@/lib/api"
import { useCurrentUser } from "@/lib/auth"
import { useT } from "@/lib/i18n"
import { jobLink, jobState, jobTitle, needsAttention, useJobActions, useJobs } from "@/lib/jobs"
import { useCancelUpdate, useUpdateProgress } from "@/lib/updates"
import { cn } from "@/lib/utils"

function JobIcon({ job }: { job: Job }) {
  if (job.status === "pending") return <Clock className="size-4 shrink-0 text-muted-foreground" />
  if (job.status === "running") return <Loader2 className="size-4 shrink-0 animate-spin" />
  return needsAttention(job)
    ? <CircleAlert className="size-4 shrink-0 text-amber-600 dark:text-amber-400" />
    : <CircleCheck className="size-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
}

function JobRow({ job, onOpen }: { job: Job; onOpen: () => void }) {
  const t = useT()
  const { cancel } = useJobActions()
  const active = isWorking(job.status)
  const onCancel = () => {
    // Cancelling a new application before it is filled in deletes it
    if (active && job.new_application && !confirm(t("jobs.confirmCancelNew"))) return
    cancel.mutate(job)
  }
  return (
    <li className="flex items-start gap-2.5 px-3 py-2.5">
      <span className="pt-0.5"><JobIcon job={job} /></span>
      <Link to={jobLink(job)} onClick={onOpen} className="min-w-0 flex-1 hover:underline">
        <span className="block truncate text-sm">{jobTitle(job)}</span>
        <span className="block text-xs text-muted-foreground">{jobState(job)}</span>
        {job.status === "failed" && job.error && (
          <span className="block truncate text-xs text-red-600 dark:text-red-400" title={job.error}>{job.error}</span>
        )}
      </Link>
      <Button variant="ghost" size="icon" className="-my-1 size-7 shrink-0" disabled={cancel.isPending}
        aria-label={active ? t("jobs.cancel") : t("jobs.dismiss")} title={active ? t("jobs.cancel") : t("jobs.dismiss")}
        onClick={onCancel}>
        <X />
      </Button>
    </li>
  )
}

function UpdateRow() {
  const t = useT()
  const me = useCurrentUser()
  const update = useUpdateProgress()
  const cancel = useCancelUpdate()
  if (!update.running) return null
  return (
    <li className="flex items-start gap-2.5 px-3 py-2.5">
      <span className="pt-0.5"><Download className="size-4 shrink-0" /></span>
      <div className="min-w-0 flex-1">
        <span className="block text-sm">{t("update.title")}</span>
        <span className="block text-xs text-muted-foreground">
          {t(`update.step.${update.step}`)} {update.progress}%
        </span>
        <ErrorText className="text-xs" error={cancel.error} />
      </div>
      {me?.role === "admin" && (
        <Button variant="ghost" size="icon" className="-my-1 size-7 shrink-0"
          disabled={!update.cancelable || cancel.isPending} aria-label={t("jobs.cancel")}
          title={update.cancelable ? t("jobs.cancel") : t("update.notCancelable")}
          onClick={() => { if (confirm(t("update.confirmCancel"))) cancel.mutate() }}>
          <X />
        </Button>
      )}
    </li>
  )
}

/** Header button with the background operations: AI jobs and the update, each with its X. */
export function JobsMenu() {
  const t = useT()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const { data: jobs = [] } = useJobs()
  const update = useUpdateProgress()
  const { cancel } = useJobActions()

  useEffect(() => {
    if (!open) return
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !ref.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener("mousedown", close)
    document.addEventListener("keydown", close)
    return () => {
      document.removeEventListener("mousedown", close)
      document.removeEventListener("keydown", close)
    }
  }, [open])

  // Waiting and running jobs in queue order, then finished ones, newest first
  const active = jobs.filter((job) => isWorking(job.status))
    .sort((a, b) => (a.status === "running" ? -1 : b.status === "running" ? 1 : (a.position ?? 0) - (b.position ?? 0)))
  const finished = jobs.filter((job) => !isWorking(job.status)).reverse()
  const updating = update.running
  const busy = active.length > 0 || updating
  const count = active.length + finished.filter(needsAttention).length + (updating ? 1 : 0)

  return (
    <div ref={ref} className="relative">
      <button type="button" aria-expanded={open} aria-label={t("jobs.title")} title={t("jobs.title")}
        onClick={() => setOpen((o) => !o)}
        className={cn("relative flex items-center rounded-md px-3 py-1.5 text-muted-foreground hover:text-foreground",
          open && "bg-secondary text-foreground")}>
        {busy ? <Loader2 className="size-4 animate-spin" /> : <ListChecks className="size-4" />}
        {count > 0 && (
          <span className="absolute -right-0.5 top-0 min-w-4 rounded-full bg-primary px-1 text-center text-[10px] font-semibold leading-4 text-primary-foreground">
            {count}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 z-20 mt-2 w-80 max-w-[calc(100vw-2rem)] overflow-hidden rounded-lg border bg-background shadow-lg">
          <div className="flex items-center justify-between border-b px-3 py-2">
            <span className="text-sm font-medium">{t("jobs.title")}</span>
            {finished.length > 0 && (
              <button type="button" className="text-xs text-muted-foreground hover:text-foreground"
                onClick={() => finished.forEach((job) => cancel.mutate(job))}>
                {t("jobs.clear")}
              </button>
            )}
          </div>
          {jobs.length === 0 && !updating ? (
            <p className="px-3 py-6 text-center text-sm text-muted-foreground">{t("jobs.empty")}</p>
          ) : (
            <ul className="max-h-96 divide-y overflow-y-auto">
              <UpdateRow />
              {[...active, ...finished].map((job) => <JobRow key={job.id} job={job} onOpen={() => setOpen(false)} />)}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
