import { type MessageKey, t } from "./i18n"

export const STATUSES = [
  { value: "applied", color: "bg-blue-500" },
  { value: "interview", color: "bg-amber-500" },
  { value: "offer", color: "bg-emerald-500" },
  { value: "rejected", color: "bg-red-500" },
  { value: "completed", color: "bg-violet-500" },
] as const

export type ApplicationStatus = (typeof STATUSES)[number]["value"]

export const statusInfo = (value: string) => STATUSES.find((s) => s.value === value) ?? STATUSES[0]
export const statusLabel = (value: string) => t(`status.${statusInfo(value).value}`)

const EVENT_TYPES = ["interview", "call", "email", "follow_up", "note", "status_change"] as const

export const eventLabel = (value: string) =>
  (EVENT_TYPES as readonly string[]).includes(value) ? t(`event.${value}` as MessageKey) : value

/** Status changes are stored as codes ("applied>interview") and rendered in the current language. */
export function eventTitle(event: { type: string; title: string }) {
  const change = event.type === "status_change" && /^(\w+)>(\w+)$/.exec(event.title)
  return change ? `${statusLabel(change[1])} → ${statusLabel(change[2])}` : event.title
}

export const WORK_MODES = ["onsite", "hybrid", "remote"] as const

export const workModeLabel = (value: string) =>
  (WORK_MODES as readonly string[]).includes(value) ? t(`workMode.${value}` as MessageKey) : value
