import type { Application } from "@/features/applications/api"
import { json, request } from "@/shared/lib/http"

interface ReportsQueued {
  queued: number
  without_skills: number
  already_queued: number
}

export const reportsApi = {
  requestReports: (ids: number[]) => request<ReportsQueued>("/api/applications/reports", json("POST", { ids })),
  requestReport: (id: number) => request<Application>(`/api/applications/${id}/report`, { method: "POST" }),
}
