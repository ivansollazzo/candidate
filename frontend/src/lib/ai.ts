import { useMutation, useQuery } from "@tanstack/react-query"
import { useEffect, useState } from "react"

import { type AITask, api, isWorking } from "./api"
import { t, useT } from "./i18n"

export const ACCELERATOR_NAMES: Record<string, string> = { cpu: "CPU", cuda: "CUDA", rocm: "ROCm", vulkan: "Vulkan" }

export const MODEL_NAMES: Record<string, string> = {
  "gemma4:e2b": "Gemma 4 E2B",
  "gemma4:e4b": "Gemma 4 E4B",
  "qwen3.5:4b": "Qwen 3.5 4B",
}
const modelName = (model: string | null | undefined) => (model ? MODEL_NAMES[model] ?? model : "")

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
  else if (llm.starting && llm.download) reason = t("ai.downloading", { model: modelName(llm.download.model) })
  else if (llm.starting) reason = t("ai.starting")
  else if (!llm.reachable) reason = t("ai.unreachable")
  else if (!llm.model_available) reason = t("ai.notDownloaded", { model: modelName(llm.model) })
  const accelerator = llm?.accelerator ? ACCELERATOR_NAMES[llm.accelerator] ?? llm.accelerator : null
  return {
    enabled: llm?.enabled ?? false,
    ready: reason == null,
    reason,
    /** Short model status, for settings */
    label: !llm ? t("ai.backendDown")
      : !llm.enabled ? t("ai.off")
        : llm.starting && llm.download
          ? t("ai.downloadingShort", { model: modelName(llm.download.model), progress: llm.download.progress })
          : llm.starting ? t("ai.startingShort")
            : reason ?? [modelName(llm.model), accelerator].filter(Boolean).join(" · "),
    tone: reason == null ? "bg-emerald-500" : !llm?.enabled ? "bg-slate-400" : llm.starting ? "bg-amber-500" : "bg-red-500",
  }
}

/**
 * Runs an LLM fill and polls it until it finishes. The result is merged with `current`
 * (the form as the user sees it) and handed to `apply`, which puts it in the form without saving.
 */
export function useAiFill<T extends object>(current: T, apply: (changes: Partial<T>, sourceText: string | null) => void) {
  const [task, setTask] = useState<AITask<Partial<T>> | null>(null)
  const [error, setError] = useState<string | null>(null)
  const start = useMutation({
    mutationFn: (run: () => Promise<AITask<Partial<T>>>) => run(),
    onMutate: () => setError(null),
    onSuccess: setTask,
    onError: (e) => setError(e.message),
  })
  const { data: polled } = useQuery({
    queryKey: ["ai-task", task?.id],
    queryFn: () => api.getTask<Partial<T>>(task!.id),
    enabled: task != null,
    refetchInterval: (q) => (isWorking(q.state.data?.status ?? "pending") ? 2000 : false),
  })

  useEffect(() => {
    if (!task || polled?.id !== task.id || isWorking(polled.status)) return
    // Merged outside any state setter, since mergeAiResult may ask the user to confirm
    if (polled.status === "done" && polled.result) apply(mergeAiResult(current, polled.result), task.source_text)
    else setError(polled.error ?? t("ai.fillFailed"))
    setTask(null)
  }, [polled, task]) // current and apply change on every render: only the result's arrival matters

  return {
    run: (fn: () => Promise<AITask<Partial<T>>>) => start.mutate(fn),
    running: start.isPending || task != null,
    error,
  }
}

const isEmpty = (v: unknown) => v == null || v === "" || (Array.isArray(v) && v.length === 0)

/** Fields to put in the form: empty ones always, filled ones only if the user confirms. */
function mergeAiResult<T extends object>(current: T, result: Partial<T>): Partial<T> {
  const entries = Object.entries(result).filter(([, v]) => !isEmpty(v)) as [keyof T, T[keyof T]][]
  const conflicts = entries.filter(([k, v]) => !isEmpty(current[k]) && JSON.stringify(current[k]) !== JSON.stringify(v))
  const overwrite = conflicts.length > 0 &&
    confirm(t("ai.confirmOverwrite", { count: conflicts.length }))
  return Object.fromEntries(entries.filter(([k]) => overwrite || isEmpty(current[k]))) as Partial<T>
}
