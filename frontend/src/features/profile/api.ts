import type { Job } from "@/features/background_jobs/api"
import { json, request, upload } from "@/shared/lib/http"
import type { SkillLevel } from "@/shared/lib/skills"

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
  /** null until the profile is saved for the first time */
  id: number | null
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
  updated_at: string | null
}

export const profileApi = {
  getProfile: () => request<Profile>("/api/profile"),
  updateProfile: (changes: Partial<Profile>) => request<Profile>("/api/profile", json("PATCH", changes)),
  uploadCv: (file: File) => request<Profile>("/api/profile/cv", upload("PUT", file)),
  fillProfile: () => request<Job>("/api/profile/fills", { method: "POST" }),
}
