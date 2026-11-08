import { request } from "@/shared/lib/http"

/** Progress of the updater service, see updater/updater.sh */
interface UpdateStatus {
  status: "unavailable" | "idle" | "checking" | "updating"
  /** restart and verify: the services are being replaced by the new version */
  step: "backup" | "download" | "restart" | "verify" | null
  /** estimated completion of the running update, 0-100 */
  progress: number
  version: string
  build: string
}

/** A branch of the repository, with the release of its latest commit */
interface UpdateBranch {
  name: string
  version: string
  build: string
  /** its images are published: only then it can be installed */
  published: boolean
  newer: boolean
}

interface UpdateResult {
  result: "ok" | "failed"
  error: "" | "branch" | "image" | "backup" | "download" | "start"
  detail: string
  finished_at: string
}

interface CheckError {
  detail: string
  failed_at: string
}

export interface Updates extends UpdateStatus {
  /** The branch the admin picked; until then "stable" */
  selected_branch: string
  checked_at: string | null
  branches: UpdateBranch[]
  update_available: boolean
  /** AI jobs waiting or running (all users): an update can be installed only when there are none */
  active_jobs: number
  last: UpdateResult | null
  /** The last check couldn't reach the repository */
  check_error: CheckError | null
}

export const updatesApi = {
  getUpdates: () => request<Updates>("/api/updates"),
  updateStatus: () => request<UpdateStatus>("/api/updates/status"),
  checkUpdates: () => request<void>("/api/updates/checks", { method: "POST" }),
  installUpdate: () => request<void>("/api/updates/installations", { method: "POST" }),
}
