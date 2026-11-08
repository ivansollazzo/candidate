import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { type Https, httpsApi } from "@/features/https/api"

/** HTTPS settings and what the web server is doing with them (admin only). */
export function useHttps() {
  return useQuery({
    queryKey: ["https"],
    queryFn: httpsApi.getHttps,
    // Follow the web server while it loads a new configuration
    refetchInterval: (query) => (query.state.data?.state === "applying" ? 2_000 : 30_000),
  })
}

function useHttpsMutation<T>(mutationFn: (value: T) => Promise<Https>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn,
    onSuccess: (data) => queryClient.setQueryData(["https"], data),
  })
}

export const useSaveHttps = () => useHttpsMutation(httpsApi.saveHttps)
export const useUploadCertificate = () => useHttpsMutation(httpsApi.uploadCertificate)
export const useDeleteCertificate = () => useHttpsMutation(httpsApi.deleteCertificate)

const MOVE_KEY = "candidate-https-move"
// Added to the new address: there the storage of the old one isn't visible (another origin)
const ARRIVED = "#https-changed"

/** Read once when the app loads: the page was moved here because HTTPS was turned on or off. */
const arrived = (() => {
  if (window.location.hash !== ARRIVED) return false
  window.history.replaceState(null, "", window.location.pathname + window.location.search)
  try {
    sessionStorage.removeItem(MOVE_KEY)
  } catch {
    /* storage unavailable */
  }
  return true
})()

/** HTTPS was turned on or off: the sessions ended and this page moves to `target` (null: it can't, the address
 * isn't covered). Kept for the sign-in page shown meanwhile. Returns the address to move to. */
export function announceMove(target: string | null): string | null {
  try {
    sessionStorage.setItem(MOVE_KEY, JSON.stringify({ target, at: Date.now() }))
  } catch {
    /* storage unavailable: the settings page shows the notice anyway */
  }
  return target && target + ARRIVED
}

/** Why the sign-in page appeared: moved here after an HTTPS change, or a move announced in the last minute. */
export function pendingMove(): { target: string | null; arrived: boolean } | null {
  if (arrived) return { target: null, arrived: true }
  try {
    const value = JSON.parse(sessionStorage.getItem(MOVE_KEY) ?? "null")
    return value && Date.now() - value.at < 60_000 ? { target: value.target, arrived: false } : null
  } catch {
    return null
  }
}
