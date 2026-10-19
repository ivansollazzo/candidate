import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useEffect, useState } from "react"

import { api } from "./api"
import { useCurrentUser } from "./auth"

// Build running when the update started; kept across reloads while the app restarts
const STARTED_KEY = "candidate.update-from"

function readStarted() {
  try {
    return sessionStorage.getItem(STARTED_KEY)
  } catch {
    return null
  }
}

function writeStarted(build: string | null) {
  try {
    if (build) sessionStorage.setItem(STARTED_KEY, build)
    else sessionStorage.removeItem(STARTED_KEY)
  } catch {
    /* storage unavailable: the screen still follows the updater status */
  }
}

/** Branches, versions and last result (admin only). */
export function useUpdates() {
  const me = useCurrentUser()
  return useQuery({
    queryKey: ["updates"],
    queryFn: api.getUpdates,
    enabled: me?.role === "admin",
    // Follow a running check quickly, otherwise pick up the periodic checks of the updater
    refetchInterval: (query) => (query.state.data?.status === "checking" ? 2_000 : 300_000),
  })
}

export function useCheckUpdates() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: api.checkUpdates,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["updates"] }),
  })
}

export function useInstallUpdate() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ branch }: { branch: string; build: string }) => api.installUpdate(branch),
    onSuccess: (_, { build }) => {
      writeStarted(build)
      queryClient.invalidateQueries({ queryKey: ["update-status"] })
    },
  })
}

/**
 * Whether an update is running, for every signed-in user. While it runs the backend and frontend are
 * rebuilt and restarted: requests fail for a moment, and once the new build answers the page reloads.
 */
export function useUpdateProgress() {
  const [started, setStarted] = useState(readStarted)
  const queryClient = useQueryClient()
  const status = useQuery({
    queryKey: ["update-status"],
    queryFn: api.updateStatus,
    retry: false,
    refetchInterval: started ? 2_000 : 60_000,
  })
  const data = status.data

  useEffect(() => {
    if (!data) return
    if (data.status === "updating") {
      if (!started) {
        writeStarted(data.build)
        setStarted(data.build)
      }
    } else if (started) {
      writeStarted(null)
      setStarted(null)
      // A different build answers: the new version is up
      if (data.build !== started) window.location.reload()
      // Same build and nothing running: the update failed, the Updates tab shows why
      else queryClient.invalidateQueries({ queryKey: ["updates"] })
    }
  }, [data, started, queryClient])

  return {
    running: started != null,
    // While the backend restarts the status can't be read
    step: status.isError ? "restart" as const : data?.step ?? "fetch",
  }
}
