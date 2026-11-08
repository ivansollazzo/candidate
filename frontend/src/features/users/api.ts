import type { NewUser, User, UserWithKey } from "@/features/auth/api"
import { json, request, upload } from "@/shared/lib/http"

export type MeChanges = Partial<Pick<User, "username" | "email" | "language" | "theme" | "application_sort"
  | "application_filter" | "report_after_fill" | "overview_layout" | "onboarded">> & {
  /** back to the default overview */
  reset_overview?: boolean
}

type UserChanges = Partial<Pick<User, "username" | "email" | "role">> & { password?: string }

export const usersApi = {
  updateMe: (changes: MeChanges) => request<User>("/api/me", json("PATCH", changes)),
  uploadAvatar: (file: File) => request<User>("/api/me/avatar", upload("PUT", file)),
  deleteAvatar: () => request<User>("/api/me/avatar", { method: "DELETE" }),
  listUsers: () => request<User[]>("/api/users"),
  createUser: (user: NewUser) => request<UserWithKey>("/api/users", json("POST", user)),
  updateUser: (id: number, changes: UserChanges) => request<User>(`/api/users/${id}`, json("PATCH", changes)),
  deleteUser: (id: number) => request<void>(`/api/users/${id}`, { method: "DELETE" }),
}
