import { json, request } from "@/shared/lib/http"

export type HttpsMode = "off" | "internal" | "custom"

interface HttpsCertificate {
  id: string
  names: string[]
  issuer: string
  not_before: string
  not_after: string
  fingerprint: string
  self_signed: boolean
  /** Names it is served for (a name two certificates hold goes to the newest) */
  hosts: string[]
}

export interface Https {
  mode: HttpsMode
  /** Addresses of internal mode */
  hosts: string[]
  certificates: HttpsCertificate[]
  authority: { name: string; fingerprint: string; not_after: string; leaf_not_after: string | null } | null
  /** What the web server is doing compared to the settings */
  state: "off" | "active" | "applying" | "error" | "unknown"
  error: string | null
  failed_at: string | null
  /** This page was opened over HTTPS */
  secure_request: boolean
  port: number
}

export const HTTPS_AUTHORITY_URL = "/api/https/authority/certificate"

export const httpsApi = {
  getHttps: () => request<Https>("/api/https"),
  saveHttps: (settings: { mode: HttpsMode; hosts: string[] }) => request<Https>("/api/https", json("PUT", settings)),
  uploadCertificate: ({ certificate, key }: { certificate: File; key: File }) => {
    const form = new FormData()
    form.append("certificate", certificate)
    form.append("key", key)
    return request<Https>("/api/https/certificates", { method: "POST", body: form })
  },
  deleteCertificate: (id: string) => request<Https>(`/api/https/certificates/${id}`, { method: "DELETE" }),
}
