import type { PasswordPolicy } from "@/features/auth/api"
import { json, request } from "@/shared/lib/http"

export const ACCELERATORS = ["cuda", "rocm", "vulkan", "cpu"] as const

type Accelerator = (typeof ACCELERATORS)[number]

/** failed: detected, but Ollama cannot use it */
export type HardwareStatus = "available" | "unavailable" | "failed"

interface Health {
  status: string
  version: string
  build: string
  /** null while a backup is being restored */
  llm: {
    enabled: boolean
    model?: string | null
    accelerator?: Accelerator | null
    starting?: boolean
    reachable?: boolean
    model_available?: boolean
    error?: string
    /** null until the llm service has probed the hardware */
    hardware: Record<Accelerator, HardwareStatus> | null
  } | null
}

/** System settings: readable by everyone, writable by the admin only */
export interface Settings extends PasswordPolicy {
  llm_enabled: boolean
  llm_accelerator: Accelerator | "auto"
  /** Branch to update from; null = "stable" */
  update_branch: string | null
  /** Hours between update checks; 0 = only on request */
  update_check_hours: number
  session_hours: number
  /** 0 = no lockout */
  max_login_attempts: number
  lockout_minutes: number
}

export const settingsApi = {
  health: () => request<Health>("/api/health"),
  getSettings: () => request<Settings>("/api/settings"),
  updateSettings: (changes: Partial<Settings>) => request<Settings>("/api/settings", json("PATCH", changes)),
}
