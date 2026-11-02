import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useEffect, useState } from "react"

import { api, type BackupSettings, RESTORING_EVENT } from "./api"

/** Backups, schedule and last results (admin only). */
export function useBackups() {
  return useQuery({
    queryKey: ["backups"],
    queryFn: api.getBackups,
    // Follow a backup while it is written
    refetchInterval: (query) => (query.state.data?.running ? 2_000 : 60_000),
  })
}

function useBackupMutation<T>(mutationFn: (value: T) => Promise<unknown>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn,
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["backups"] }),
  })
}

/** Saves the schedule with the time zone of this browser, so the hour means what the admin sees. */
export const useSaveBackupSettings = () => useBackupMutation((settings: BackupSettings) =>
  api.saveBackupSettings({ ...settings, timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC" }))

export const useCreateBackup = () => useBackupMutation(api.createBackup)

export const useDeleteBackup = () => useBackupMutation(api.deleteBackup)

export function useRestoreBackup() {
  return useMutation({
    mutationFn: api.restoreBackup,
    // The app is in maintenance from now on: show the restore screen at once
    onSuccess: () => window.dispatchEvent(new Event(RESTORING_EVENT)),
  })
}

/**
 * Whether a backup is being restored. Any request answered with "restoring" turns it on; then the health
 * check is polled and the page reloads once the backend is back, to start again from the restored data.
 */
export function useRestoring() {
  const [restoring, setRestoring] = useState(false)

  useEffect(() => {
    const start = () => setRestoring(true)
    window.addEventListener(RESTORING_EVENT, start)
    return () => window.removeEventListener(RESTORING_EVENT, start)
  }, [])

  useEffect(() => {
    if (!restoring) return
    const timer = window.setInterval(async () => {
      try {
        if ((await api.health()).status !== "restoring") window.location.reload()
      } catch {
        /* backend not answering for a moment: keep waiting */
      }
    }, 2_000)
    return () => window.clearInterval(timer)
  }, [restoring])

  return restoring
}
