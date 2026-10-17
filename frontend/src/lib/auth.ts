import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { ApiError, api, type MeChanges, type PasswordPolicy, type User } from "./api"
import { t } from "./i18n"

/** Current user; null if there is no session or it expired. */
export function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: async () => {
      try {
        return await api.getMe()
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return null
        throw e
      }
    },
  })
}

export const useCurrentUser = () => useMe().data ?? null

export const useAuthStatus = () => useQuery({ queryKey: ["auth-status"], queryFn: api.authStatus })

/** Saves language, theme and account details immediately. */
export function useUpdateMe() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (changes: MeChanges) => api.updateMe(changes),
    onSuccess: (user) => queryClient.setQueryData(["me"], user),
  })
}

/** Switches user without keeping the previous session's data cached. */
function useSwitchUser() {
  const queryClient = useQueryClient()
  return (user: User | null) => {
    queryClient.setQueryData(["me"], user)
    queryClient.removeQueries({ predicate: (q) => !["me", "auth-status"].includes(q.queryKey[0] as string) })
  }
}

export const useSignIn = useSwitchUser

export function useLogout() {
  const switchUser = useSwitchUser()
  return useMutation({ mutationFn: api.logout, onSettled: () => switchUser(null) })
}

/** Password rules still unmet, mirroring the backend checks. */
export function passwordProblems(password: string, policy: PasswordPolicy): string[] {
  const problems: string[] = []
  if (password.length < policy.password_min_length) problems.push(t("password.length", { count: policy.password_min_length }))
  if (policy.password_require_uppercase && !/[A-Z]/.test(password)) problems.push(t("password.uppercase"))
  if (policy.password_require_digit && !/\d/.test(password)) problems.push(t("password.digit"))
  if (policy.password_require_symbol && !/[^A-Za-z0-9]/.test(password)) problems.push(t("password.symbol"))
  return problems
}

/** Profile photo URL; the query param changes when the user is updated, so the browser doesn't show a stale one. */
export function avatarUrl(user: User, viewer: User | null) {
  const path = viewer?.id === user.id ? "/api/me/avatar" : `/api/users/${user.id}/avatar`
  return `${path}?v=${encodeURIComponent(user.updated_at)}`
}
