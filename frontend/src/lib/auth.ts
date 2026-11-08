import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { ApiError, api, type MeChanges, type PasswordPolicy, type User } from "./api"
import { t } from "./i18n"

// A session was open in this tab: a 401 then means it ended (expired, closed by HTTPS turned on or off, password
// changed elsewhere), which the sign-in page says instead of showing up without a word
let hadSession = false
let sessionEnded = false

/** True once after a session ended by itself; read by the sign-in page. */
export function takeSessionEnded() {
  const ended = sessionEnded
  sessionEnded = false
  return ended
}

/** Current user; null if there is no session or it expired. */
export function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: async () => {
      try {
        const user = await api.getMe()
        hadSession = true
        return user
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) {
          sessionEnded ||= hadSession
          hadSession = false
          return null
        }
        throw e
      }
    },
  })
}

/** After signing in: the browser must send the new session cookie back, or every request would fail and the
 * sign-in page come back without a reason. */
export async function confirmSession<T>(result: T): Promise<T> {
  try {
    await api.getMe()
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) throw new ApiError(t("login.sessionNotKept"), 401)
    throw e
  }
  return result
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

/** Saves a preference of the user: applied at once, stored in the background. */
export function useSavePreference() {
  const queryClient = useQueryClient()
  const updateMe = useUpdateMe()
  return (changes: MeChanges) => {
    const { reset_overview, ...fields } = changes
    queryClient.setQueryData<User>(["me"], (old) => old && { ...old, ...fields, ...(reset_overview ? { overview_layout: null } : {}) })
    updateMe.mutate(changes)
  }
}

/** Switches user without keeping the previous session's data cached. */
function useSwitchUser() {
  const queryClient = useQueryClient()
  return (user: User | null) => {
    hadSession = user != null
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
