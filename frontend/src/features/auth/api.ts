import type { ApplicationStatus } from "@/features/applications/status"
import { json, request } from "@/shared/lib/http"
import type { Locale } from "@/shared/lib/i18n"

export interface PasswordPolicy {
  password_min_length: number
  password_require_uppercase: boolean
  password_require_digit: boolean
  password_require_symbol: boolean
}

export type Role = "admin" | "user"

export type Theme = "light" | "dark" | "system"

export type ApplicationSort = "applied" | "status" | "name" | "event"

type ApplicationFilter = "all" | ApplicationStatus

export type WidgetId = "counts" | "calendar" | "events" | "recent" | "profile" | "weekly" | "top_matches"
  | "stale_reports" | "missing_skills"

export interface OverviewWidget {
  id: WidgetId
  size: "half" | "full"
}

export interface User {
  id: number
  username: string
  email: string
  role: Role
  language: Locale
  theme: Theme
  application_sort: ApplicationSort
  /** status shown in the applications list */
  application_filter: ApplicationFilter
  /** new applications filled by the AI also get their compatibility report */
  report_after_fill: boolean
  /** widgets of the overview in order; null for the default layout */
  overview_layout: OverviewWidget[] | null
  /** false until the initial setup is completed */
  onboarded: boolean
  has_avatar: boolean
  created_at: string
  updated_at: string
}

/** Newly created or recovered user: the recovery key is only returned now */
export interface UserWithKey {
  user: User
  recovery_key: string
}

interface AuthStatus {
  setup_required: boolean
  password_policy: PasswordPolicy
}

export type NewUser = Pick<User, "username" | "email" | "role" | "language"> & { password: string }

export const authApi = {
  authStatus: () => request<AuthStatus>("/api/setup"),
  setup: (account: Omit<NewUser, "role">) => request<UserWithKey>("/api/setup", json("POST", account)),
  login: (username: string, password: string) => request<User>("/api/session", json("POST", { username, password })),
  logout: () => request<void>("/api/session", { method: "DELETE" }),
  resetPassword: (username: string, recovery_key: string, new_password: string) =>
    request<UserWithKey>("/api/password-resets", json("POST", { username, recovery_key, new_password })),
  getMe: () => request<User>("/api/me"),
  changePassword: (current_password: string, new_password: string) =>
    request<User>("/api/me/password", json("PUT", { current_password, new_password })),
  newRecoveryKey: (password: string) => request<{ recovery_key: string }>("/api/me/recovery-key", json("POST", { password })),
}
