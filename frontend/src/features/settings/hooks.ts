import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { useCurrentUser } from "@/features/auth/hooks"
import { type Settings, settingsApi } from "@/features/settings/api"

/** System settings, loaded after login. */
export const useSettings = () =>
  useQuery({ queryKey: ["settings"], queryFn: settingsApi.getSettings, enabled: useCurrentUser() != null }).data

/** Saves settings changes immediately (admin only). */
export function useUpdateSettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (changes: Partial<Settings>) => settingsApi.updateSettings(changes),
    onSuccess: (data) => {
      queryClient.setQueryData(["settings"], data)
      // LLM status, password rules and available updates depend on the settings
      queryClient.invalidateQueries({ queryKey: ["health"] })
      queryClient.invalidateQueries({ queryKey: ["auth-status"] })
      queryClient.invalidateQueries({ queryKey: ["updates"] })
      // Turning AI off deletes the compatibility reports
      queryClient.invalidateQueries({ queryKey: ["application"] })
    },
  })
}
