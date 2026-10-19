import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api, type Settings } from "./api"
import { useCurrentUser } from "./auth"

/** System settings, loaded after login. */
export const useSettings = () =>
  useQuery({ queryKey: ["settings"], queryFn: api.getSettings, enabled: useCurrentUser() != null }).data

/** Saves settings changes immediately (admin only). */
export function useUpdateSettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (changes: Partial<Settings>) => api.updateSettings(changes),
    onSuccess: (data) => {
      queryClient.setQueryData(["settings"], data)
      // LLM status, password rules and available updates depend on the settings
      queryClient.invalidateQueries({ queryKey: ["health"] })
      queryClient.invalidateQueries({ queryKey: ["auth-status"] })
      queryClient.invalidateQueries({ queryKey: ["updates"] })
    },
  })
}
