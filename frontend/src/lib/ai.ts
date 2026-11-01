import { useQuery } from "@tanstack/react-query"

import { api } from "./api"
import { useT } from "./i18n"

export const ACCELERATOR_NAMES: Record<string, string> = { cpu: "CPU", cuda: "CUDA", rocm: "ROCm", vulkan: "Vulkan" }

/** Backend status: release and LLM state. */
export const useHealth = () => useQuery({ queryKey: ["health"], queryFn: api.health, refetchInterval: 30_000 })

/** Whether the LLM can be used right now and, if not, why. */
export function useAiStatus() {
  const t = useT()
  const { data } = useHealth()
  const llm = data?.llm
  let reason: string | null = null
  if (!llm) reason = t("ai.backendDown")
  else if (!llm.enabled) reason = t("ai.disabled")
  else if (llm.starting) reason = t("ai.starting")
  else if (!llm.reachable) reason = t("ai.unreachable")
  else if (!llm.model_available) reason = t("ai.notDownloaded", { model: llm.model ?? "" })
  const accelerator = llm?.accelerator ? ACCELERATOR_NAMES[llm.accelerator] ?? llm.accelerator : null
  return {
    enabled: llm?.enabled ?? false,
    ready: reason == null,
    reason,
    /** Short model status, for settings */
    label: !llm ? t("ai.backendDown")
      : !llm.enabled ? t("ai.off")
        : llm.starting ? t("ai.startingShort")
          : reason ?? [llm.model, accelerator].filter(Boolean).join(" · "),
    tone: reason == null ? "bg-emerald-500" : !llm?.enabled ? "bg-slate-400" : llm.starting ? "bg-amber-500" : "bg-red-500",
  }
}
