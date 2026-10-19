import { getLocale, type Locale, t } from "./i18n"
import type { ApplicationStatus } from "./status"

type JobSkill = { name: string; importance: "required" | "nice_to_have" | string }
type TaskStatus = "pending" | "running" | "done" | "failed"

export interface ApplicationSummary {
  id: number
  title: string | null
  company: string | null
  location: string | null
  work_mode: string | null
  salary: string | null
  salary_period: "annual" | "monthly" | "daily" | "hourly" | null
  salary_basis: "gross" | "net" | null
  status: ApplicationStatus
  applied_on: string | null
  created_at: string
  updated_at: string
}

export interface ApplicationListItem extends ApplicationSummary {
  /** Date of the latest agenda event, status changes excluded */
  last_event_on: string | null
}

export interface ApplicationEvent {
  id: number
  application_id: number
  type: string
  occurred_on: string
  /** "HH:MM:SS" or null */
  starts_at: string | null
  title: string
  details: string | null
  completed: boolean
  created_at: string
}

/** Event with its application's data, for the agenda and overview */
export interface AgendaEvent extends ApplicationEvent {
  application_title: string | null
  application_company: string | null
}

export type EventFields = Pick<ApplicationEvent, "application_id" | "type" | "occurred_on" | "starts_at" | "title" | "details" | "completed">

interface Advice {
  summary?: string
  strengths?: string[]
  improvements?: { skill: string; suggestion: string }[]
  score?: number
  error?: string
}

export interface Application extends ApplicationSummary {
  contract_type: string | null
  seniority: string | null
  responsibilities: string[]
  requirements: string[]
  nice_to_have: string[]
  benefits: string[]
  skills: JobSkill[]
  languages: string[]
  education_required: string | null
  experience_years_min: number | null
  source_url: string | null
  contact_name: string | null
  contact_email: string | null
  notes: string | null
  has_description: boolean
  advice: Advice | null
  advice_status: TaskStatus | null
  events: ApplicationEvent[]
}

export type SkillLevel = 1 | 2 | 3 | 4
/** level null: skill added from projects; the user sets the level */
export type ProfileSkill = { name: string; category?: string | null; level: SkillLevel | null; evidence?: string | null }

export interface Experience {
  role?: string | null
  company?: string | null
  location?: string | null
  employment_type?: string | null
  start?: string | null
  end?: string | null
  current?: boolean
  description?: string | null
  technologies?: string[]
}

export interface Education {
  degree?: string | null
  field_of_study?: string | null
  institution?: string | null
  location?: string | null
  start?: string | null
  end?: string | null
  grade?: string | null
  thesis?: string | null
  details?: string | null
}

export interface Project {
  name: string
  context?: string | null
  team?: string | null
  start?: string | null
  end?: string | null
  description?: string | null
  technologies: string[]
}

export interface Certification {
  name: string
  issuer?: string | null
  issued_on?: string | null
  expires_on?: string | null
  credential_id?: string | null
  url?: string | null
}

export type Language = { language: string; level?: string | null }
export type ProfileLink = { label?: string | null; url: string }

export interface Profile {
  id: number
  full_name: string | null
  email: string | null
  phone: string | null
  location: string | null
  headline: string | null
  summary: string | null
  years_of_experience: number | null
  links: ProfileLink[]
  skills: ProfileSkill[]
  experiences: Experience[]
  education: Education[]
  projects: Project[]
  certifications: Certification[]
  languages: Language[]
  cv_filename: string | null
  updated_at: string
}

export interface SkillMatchItem {
  skill: string
  importance: string
  status: "match" | "partial" | "missing"
  matched_with: string | null
  similarity: number | null
  level: SkillLevel | null
  note: string | null
}

interface MatchResult {
  score: number
  matched: SkillMatchItem[]
  partial: SkillMatchItem[]
  missing: SkillMatchItem[]
  has_profile: boolean
}

export const ACCELERATORS = ["cuda", "rocm", "vulkan", "cpu"] as const
type Accelerator = (typeof ACCELERATORS)[number]
/** failed: detected, but Ollama cannot use it */
export type HardwareStatus = "available" | "unavailable" | "failed"

interface Health {
  status: string
  version: string
  build: string
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
  }
}

export interface PasswordPolicy {
  password_min_length: number
  password_require_uppercase: boolean
  password_require_digit: boolean
  password_require_symbol: boolean
}

/** Progress of the updater service, see updater/updater.sh */
export interface UpdateStatus {
  status: "unavailable" | "idle" | "checking" | "updating"
  step: "fetch" | "build" | "cleanup" | null
  /** estimated completion of the running update, 0-100 */
  progress: number
  version: string
  build: string
}

export interface BranchRelease {
  name: string
  version: string
  build: string
  commit: string
  newer: boolean
}

export interface UpdateResult {
  result: "ok" | "failed"
  error: "" | "fetch" | "branch" | "checkout" | "build"
  detail: string
  restart_required: boolean
  stashed: boolean
  finished_at: string
}

export interface Updates extends UpdateStatus {
  branch: string | null
  followed_branch: string | null
  commit: string | null
  checked_at: string | null
  branches: BranchRelease[]
  update_available: boolean
  last: UpdateResult | null
}

/** System settings: readable by everyone, writable by the admin only */
export interface Settings extends PasswordPolicy {
  llm_enabled: boolean
  llm_accelerator: Accelerator | "auto"
  /** Branch followed for updates; null = the one checked out */
  update_branch: string | null
  /** Hours between update checks; 0 = only on request */
  update_check_hours: number
  session_hours: number
  /** 0 = no lockout */
  max_login_attempts: number
  lockout_minutes: number
}

export type Role = "admin" | "user"
export type Theme = "light" | "dark" | "system"
export type ApplicationBulk =
  | { ids: number[]; action: "delete" }
  | { ids: number[]; action: "status"; status: ApplicationStatus }

export type ApplicationSort = "applied" | "status" | "name" | "event"
export type ApplicationFilter = "all" | ApplicationStatus

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

export type MeChanges = Partial<Pick<User, "username" | "email" | "language" | "theme" | "application_sort" | "application_filter" | "onboarded">>
type NewUser = Pick<User, "username" | "email" | "role" | "language"> & { password: string }
type UserChanges = Partial<Pick<User, "username" | "email" | "role">> & { password?: string }

export interface AITask<T = Record<string, unknown>> {
  id: string
  status: TaskStatus
  result: T | null
  error: string | null
  source_text: string | null
}

/** Where to read the job posting for the LLM fill */
export type JobSource = { text: string } | { url: string } | { file: File } | { application_id: number }

/** Editable application fields, plus the job posting text to store */
export type ApplicationChanges = Partial<Application> & { description?: string | null }

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message)
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // Language drives backend error messages and generated text
  const res = await fetch(path, { ...init, headers: { ...init?.headers, "Accept-Language": getLocale() } })
  if (!res.ok) {
    let message = t("common.error", { status: res.status })
    try {
      const body = await res.json()
      if (typeof body.detail === "string") message = body.detail
      else if (Array.isArray(body.detail)) message = body.detail.map((d: { msg: string }) => d.msg).join(", ")
    } catch {
      /* non-JSON response */
    }
    throw new ApiError(message, res.status)
  }
  return res.status === 204 ? (undefined as T) : res.json()
}

const upload = (method: string, file: File): RequestInit => {
  const form = new FormData()
  form.append("file", file)
  return { method, body: form }
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
})

export const api = {
  health: () => request<Health>("/api/health"),

  authStatus: () => request<AuthStatus>("/api/auth/status"),
  setup: (account: Omit<NewUser, "role">) => request<UserWithKey>("/api/auth/setup", json("POST", account)),
  login: (username: string, password: string) => request<User>("/api/auth/login", json("POST", { username, password })),
  logout: () => request<void>("/api/auth/logout", { method: "POST" }),
  resetPassword: (username: string, recovery_key: string, new_password: string) =>
    request<UserWithKey>("/api/auth/reset", json("POST", { username, recovery_key, new_password })),

  getMe: () => request<User>("/api/me"),
  updateMe: (changes: MeChanges) => request<User>("/api/me", json("PATCH", changes)),
  changePassword: (current_password: string, new_password: string) =>
    request<User>("/api/me/password", json("POST", { current_password, new_password })),
  newRecoveryKey: (password: string) => request<{ recovery_key: string }>("/api/me/recovery-key", json("POST", { password })),
  uploadAvatar: (file: File) => request<User>("/api/me/avatar", upload("PUT", file)),
  deleteAvatar: () => request<User>("/api/me/avatar", { method: "DELETE" }),

  listUsers: () => request<User[]>("/api/users"),
  createUser: (user: NewUser) => request<UserWithKey>("/api/users", json("POST", user)),
  updateUser: (id: number, changes: UserChanges) => request<User>(`/api/users/${id}`, json("PATCH", changes)),
  deleteUser: (id: number) => request<void>(`/api/users/${id}`, { method: "DELETE" }),

  listApplications: () => request<ApplicationListItem[]>("/api/applications"),
  getApplication: (id: number) => request<Application>(`/api/applications/${id}`),
  createApplication: (fields: ApplicationChanges) => request<Application>("/api/applications", json("POST", fields)),
  updateApplication: (id: number, changes: ApplicationChanges) =>
    request<Application>(`/api/applications/${id}`, json("PATCH", changes)),
  deleteApplication: (id: number) => request<void>(`/api/applications/${id}`, { method: "DELETE" }),
  /** Same action on several applications: all of them or none */
  bulkApplications: (bulk: ApplicationBulk) => request<void>("/api/applications/bulk", json("POST", bulk)),
  getMatch: (id: number) => request<MatchResult>(`/api/applications/${id}/match`),
  requestAdvice: (id: number) => request<Application>(`/api/applications/${id}/advice`, { method: "POST" }),

  listEvents: () => request<AgendaEvent[]>("/api/events"),
  addEvent: (event: EventFields) => request<ApplicationEvent>("/api/events", json("POST", event)),
  updateEvent: (id: number, changes: Partial<EventFields>) => request<ApplicationEvent>(`/api/events/${id}`, json("PATCH", changes)),
  deleteEvent: (id: number) => request<void>(`/api/events/${id}`, { method: "DELETE" }),

  getProfile: () => request<Profile>("/api/profile"),
  updateProfile: (changes: Partial<Profile>) => request<Profile>("/api/profile", json("PATCH", changes)),
  uploadCv: (file: File) => request<Profile>("/api/profile/cv", upload("POST", file)),

  fillJobPosting: (source: JobSource) => {
    const form = new FormData()
    for (const [key, value] of Object.entries(source)) form.append(key, value instanceof File ? value : String(value))
    return request<AITask<Partial<Application>>>("/api/ai/job-posting", { method: "POST", body: form })
  },
  fillFromCv: () => request<AITask<Partial<Profile>>>("/api/ai/cv", { method: "POST" }),
  getTask: <T>(id: string) => request<AITask<T>>(`/api/ai/tasks/${id}`),

  getSettings: () => request<Settings>("/api/settings"),
  updateSettings: (changes: Partial<Settings>) => request<Settings>("/api/settings", json("PATCH", changes)),

  getUpdates: () => request<Updates>("/api/updates"),
  updateStatus: () => request<UpdateStatus>("/api/updates/status"),
  checkUpdates: () => request<void>("/api/updates/check", { method: "POST" }),
  installUpdate: () => request<void>("/api/updates/install", { method: "POST" }),
}

export const isWorking = (status: TaskStatus | null | undefined) => status === "pending" || status === "running"
