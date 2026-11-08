import { getLocale, t } from "@/shared/lib/i18n"

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message)
  }
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // Language drives backend error messages and generated text
  const res = await fetch(path, { ...init, headers: { ...init?.headers, "Accept-Language": getLocale() } })
  if (!res.ok) {
    let message = t("common.error", { status: res.status })
    try {
      const body = await res.json()
      if (res.status === 503 && body.code === "restoring") window.dispatchEvent(new Event(RESTORING_EVENT))
      if (typeof body.detail === "string") message = body.detail
      else if (Array.isArray(body.detail)) message = body.detail.map((d: { msg: string }) => d.msg).join(", ")
    } catch {
      /* non-JSON response */
    }
    throw new ApiError(message, res.status)
  }
  return res.status === 204 ? (undefined as T) : res.json()
}

export const upload = (method: string, file: File): RequestInit => {
  const form = new FormData()
  form.append("file", file)
  return { method, body: form }
}

export const uploadMany = (method: string, files: File[]): RequestInit => {
  const form = new FormData()
  for (const file of files) form.append("files", file)
  return { method, body: form }
}

export const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
})

/** Fired when the backend answers that a backup is being restored */
export const RESTORING_EVENT = "candidate:restoring"

export type TaskStatus = "pending" | "running" | "done" | "failed"

export const isWorking = (status: TaskStatus | null | undefined) => status === "pending" || status === "running"
