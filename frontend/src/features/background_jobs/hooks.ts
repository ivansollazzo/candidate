import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useEffect, useRef } from "react"

import { type Job, jobsApi } from "@/features/background_jobs/api"
import { isWorking } from "@/shared/lib/http"
import { t } from "@/shared/lib/i18n"
import { toast } from "@/shared/lib/toast"

/** The user's background jobs; followed closely while one is waiting or running. */
export function useJobs() {
  return useQuery({
    queryKey: ["jobs"],
    queryFn: jobsApi.listJobs,
    refetchInterval: (query) => (query.state.data?.some((job) => isWorking(job.status)) ? 2_000 : 30_000),
  })
}

/** Latest job of a kind, for an application or for the profile. */
export function findJob(jobs: Job[] | undefined, kind: Job["kind"], applicationId?: number) {
  return jobs?.filter((job) => job.kind === kind && (applicationId == null || job.application_id === applicationId)).at(-1)
}

/** Finished jobs that need the user: failed, or with values to review. */
export const needsAttention = (job: Job) => job.status === "failed" || (job.status === "done" && job.proposal != null)

export function jobTitle(job: Job) {
  if (job.kind === "profile") return t("jobs.profile")
  const title = job.application_title ?? (job.new_application ? t("jobs.newApplication") : t("application.untitled"))
  return job.kind === "report" ? t("jobs.report", { title }) : title
}

export function jobLink(job: Job) {
  return job.kind === "profile" ? "/profile" : `/applications/${job.application_id}`
}

export function jobState(job: Job) {
  if (job.status === "pending") return t("jobs.queued", { position: job.position ?? 1 })
  if (job.status === "running") return t("jobs.running")
  if (job.status === "failed") return t("jobs.failed")
  return job.proposal ? t("jobs.review", { count: Object.keys(job.proposal).length }) : t("jobs.done")
}

function toastTone(job: Job) {
  if (job.status === "failed") return "error"
  return job.proposal ? "warning" : "success"
}

/** What a finished job's notice says: the outcome, then what it concerns. */
function toastText(job: Job) {
  const failed = job.status === "failed"
  const review = job.proposal ? t("jobs.review", { count: Object.keys(job.proposal).length }) : undefined
  if (job.kind === "profile") {
    return { title: failed ? t("toast.profileFailed") : t("toast.profileDone"), description: review }
  }
  const name = job.application_title ?? (job.new_application ? t("jobs.newApplication") : t("application.untitled"))
  if (job.kind === "report") {
    return { title: failed ? t("toast.reportFailed") : t("toast.reportDone"), description: name }
  }
  return {
    title: failed ? t("jobs.fillFailed") : t("toast.applicationDone"),
    description: review ? `${name} · ${review}` : name,
  }
}

/** Refreshes what a job changed, after it is cancelled, applied or retried, or once it finishes. */
function useRefresh() {
  const queryClient = useQueryClient()
  return (job?: Job) => {
    queryClient.invalidateQueries({ queryKey: ["jobs"] })
    queryClient.invalidateQueries({ queryKey: ["applications"] })
    if (job?.application_id != null) queryClient.invalidateQueries({ queryKey: ["application", job.application_id] })
    if (job?.kind === "profile") queryClient.invalidateQueries({ queryKey: ["profile"] })
  }
}

export function useJobActions() {
  const refresh = useRefresh()
  const options = { onSettled: (_data: unknown, _error: Error | null, job: Job) => refresh(job) }
  return {
    cancel: useMutation({ mutationFn: (job: Job) => jobsApi.cancelJob(job.id), ...options }),
    apply: useMutation({ mutationFn: (job: Job) => jobsApi.applyJob(job.id), ...options }),
    retry: useMutation({ mutationFn: (job: Job) => jobsApi.retryJob(job.id), ...options }),
  }
}

/** Mounted once: when a job finishes, refreshes the data it changed and shows a notice. */
export function useJobWatcher() {
  const { data } = useJobs()
  const refresh = useRefresh()
  const previous = useRef<Map<number, Job> | null>(null)

  useEffect(() => {
    if (!data) return
    const before = previous.current
    previous.current = new Map(data.map((job) => [job.id, job]))
    // Nothing to report about the jobs found when the page opens
    if (!before) return
    for (const job of data) {
      const old = before.get(job.id)
      if (!old || !isWorking(old.status) || isWorking(job.status)) continue
      refresh(job)
      toast({ ...toastText(job), tone: toastTone(job), to: jobLink(job) })
    }
  }, [data])
}
