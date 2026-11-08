import { useMutation, useQueryClient } from "@tanstack/react-query"

import { type ApplicationEvent, applicationsApi, type EventFields } from "@/features/applications/api"
import { t } from "@/shared/lib/i18n"
import { today } from "@/shared/lib/utils"

/** Schedulable types; status changes are recorded by the backend. */
export const SCHEDULABLE_TYPES = ["interview", "call", "email", "follow_up", "note"] as const

/** "15:30:00" → "15:30" */
const formatTime = (value: string | null) => value?.slice(0, 5) ?? null

/** "15:00" or "15:00–16:00"; null without a start time */
export function timeRange(event: Pick<ApplicationEvent, "starts_at" | "ends_at">) {
  if (!event.starts_at) return null
  return event.ends_at ? `${formatTime(event.starts_at)}–${formatTime(event.ends_at)}` : formatTime(event.starts_at)
}

/** "HH:MM" plus some minutes, or null past midnight (an event ends on its own day) */
export function addMinutes(time: string, minutes: number) {
  const [h, m] = time.split(":").map(Number)
  const total = h * 60 + m + minutes
  if (total >= 24 * 60) return null
  return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`
}

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
    add: useMutation({ mutationFn: (fields: EventFields) => applicationsApi.addEvent(fields), onSuccess }),
    update: useMutation({
      mutationFn: ({ id, changes }: { id: number; changes: Partial<EventFields> }) => applicationsApi.updateEvent(id, changes),
      onSuccess,
    }),
    remove: useMutation({ mutationFn: (id: number) => applicationsApi.deleteEvent(id), onSuccess }),
  }
}
