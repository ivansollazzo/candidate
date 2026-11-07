import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api, type Https } from "./api"

/** HTTPS settings and what the web server is doing with them (admin only). */
export function useHttps() {
  return useQuery({
    queryKey: ["https"],
    queryFn: api.getHttps,
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

export const useSaveHttps = () => useHttpsMutation(api.saveHttps)
export const useUploadCertificate = () => useHttpsMutation(api.uploadCertificate)
export const useDeleteCertificate = () => useHttpsMutation(api.deleteCertificate)
