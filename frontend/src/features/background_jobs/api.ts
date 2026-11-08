import { request, type TaskStatus } from "@/shared/lib/http"

/** Background LLM operation, run one at a time by the backend */
export interface Job {
  id: number
  kind: "application" | "profile" | "report"
  status: TaskStatus
  application_id: number | null
  application_title: string | null
  /** The application was created by this job: cancelling it before it is done deletes the application */
  new_application: boolean
  /** Once the application is filled, its compatibility report is queued */
  then_report: boolean
  /** Place in the queue shared by all users (1 = next), for waiting jobs */
  position: number | null
  /** Values found for fields already filled, applied only if the user confirms */
  proposal: Record<string, unknown> | null
  error: string | null
  created_at: string
  finished_at: string | null
}

export const jobsApi = {
  listJobs: () => request<Job[]>("/api/jobs"),
  /** Cancels a waiting or running job, or dismisses a finished one */
  cancelJob: (id: number) => request<void>(`/api/jobs/${id}`, { method: "DELETE" }),
  applyJob: (id: number) => request<void>(`/api/jobs/${id}/accept`, { method: "POST" }),
  retryJob: (id: number) => request<Job>(`/api/jobs/${id}/retry`, { method: "POST" }),
}
