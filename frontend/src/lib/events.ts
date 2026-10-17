import { useMutation, useQueryClient } from "@tanstack/react-query"

import { api, type ApplicationEvent, type EventFields } from "./api"
import { t } from "./i18n"
import { today } from "./utils"

/** Schedulable types; status changes are recorded by the backend. */
export const SCHEDULABLE_TYPES = ["interview", "call", "email", "follow_up", "note"] as const

/** "15:30:00" → "15:30" */
export const formatTime = (value: string | null) => value?.slice(0, 5) ?? null

export const isOverdue = (event: Pick<ApplicationEvent, "completed" | "occurred_on">) =>
  !event.completed && event.occurred_on < today()

/** "today", "tomorrow", "in 3 days"; null for past dates or more than a week ahead */
export function relativeDay(value: string) {
  const days = Math.round((Date.parse(value) - Date.parse(today())) / 86_400_000)
  if (days < 0 || days > 7) return null
  return days === 0 ? t("overview.today") : days === 1 ? t("overview.tomorrow") : t("overview.inDays", { days })
}

/** Event create/update/delete; each refreshes the agenda, overview and detail views. */
export function useEventMutations() {
  const queryClient = useQueryClient()
  const onSuccess = () => {
    queryClient.invalidateQueries({ queryKey: ["events"] })
    queryClient.invalidateQueries({ queryKey: ["application"] })
  }
  return {
    add: useMutation({ mutationFn: (fields: EventFields) => api.addEvent(fields), onSuccess }),
    update: useMutation({
      mutationFn: ({ id, changes }: { id: number; changes: Partial<EventFields> }) => api.updateEvent(id, changes),
      onSuccess,
    }),
    remove: useMutation({ mutationFn: (id: number) => api.deleteEvent(id), onSuccess }),
  }
}
