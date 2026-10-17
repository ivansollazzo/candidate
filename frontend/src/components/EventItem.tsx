import { CheckCircle2, Circle, Pencil, Trash2 } from "lucide-react"
import { useState } from "react"
import { Link } from "react-router"

import { EventForm } from "@/components/EventForm"
import { Button } from "@/components/ui/button"
import type { AgendaEvent, ApplicationEvent } from "@/lib/api"
import { formatTime, isOverdue, relativeDay, useEventMutations } from "@/lib/events"
import { useT } from "@/lib/i18n"
import { eventLabel, eventTitle } from "@/lib/status"
import { cn, formatDate } from "@/lib/utils"

/** Event row with complete/edit/delete; `showApplication` also shows its application. */
export function EventItem({ event, showApplication, compact }: {
  event: ApplicationEvent | AgendaEvent
  showApplication?: boolean
  /** No notes or edit buttons, for the overview */
  compact?: boolean
}) {
  const t = useT()
  const { update, remove } = useEventMutations()
  const [editing, setEditing] = useState(false)
  // Status changes are recorded by the backend: they can only be deleted
  const statusChange = event.type === "status_change"
  const overdue = isOverdue(event)
  const relative = !event.completed && relativeDay(event.occurred_on)

  if (editing) {
    return (
      <li className="rounded-lg border bg-secondary/40 p-3">
        <EventForm initial={event} saving={update.isPending} error={update.error?.message} onCancel={() => setEditing(false)}
          onSubmit={(changes) => update.mutate({ id: event.id, changes }, { onSuccess: () => setEditing(false) })} />
      </li>
    )
  }

  const application = "application_title" in event && showApplication
    ? [event.application_title ?? t("application.untitled"), event.application_company].filter(Boolean).join(" · ")
    : null

  return (
    <li className="group flex items-start gap-2.5">
      {statusChange ? (
        <span className="mt-1.5 flex size-5 shrink-0 items-center justify-center">
          <span className="size-2 rounded-full bg-muted-foreground" />
        </span>
      ) : (
        <button type="button" className="mt-0.5 shrink-0 text-muted-foreground hover:text-foreground disabled:opacity-50"
          aria-label={event.completed ? t("eventItem.markTodo") : t("eventItem.markDone")}
          title={event.completed ? t("eventItem.markTodo") : t("eventItem.markDone")} disabled={update.isPending}
          onClick={() => update.mutate({ id: event.id, changes: { completed: !event.completed } })}>
          {event.completed ? <CheckCircle2 className="size-5 text-emerald-600 dark:text-emerald-400" /> : <Circle className="size-5" />}
        </button>
      )}
      <div className="min-w-0 flex-1">
        <p className={cn("text-sm font-medium", event.completed && !statusChange && "text-muted-foreground line-through")}>
          {eventTitle(event)}
        </p>
        <p className="flex flex-wrap gap-x-1.5 text-xs text-muted-foreground">
          <span className={cn(overdue && "font-medium text-red-600 dark:text-red-400")}>
            {formatDate(event.occurred_on)}{event.starts_at && `, ${formatTime(event.starts_at)}`}
          </span>
          {overdue && <span className="font-medium text-red-600 dark:text-red-400">· {t("eventItem.overdue")}</span>}
          {relative && <span className="text-foreground">· {relative}</span>}
          <span>· {eventLabel(event.type)}</span>
        </p>
        {application && (
          <Link to={`/applications/${event.application_id}`} className="block truncate text-xs underline-offset-2 hover:underline">
            {application}
          </Link>
        )}
        {!compact && event.details && <p className="mt-0.5 whitespace-pre-wrap text-sm text-muted-foreground">{event.details}</p>}
      </div>
      {!compact && (
        <div className="flex opacity-60 group-hover:opacity-100">
          {!statusChange && (
            <Button variant="ghost" size="icon" aria-label={t("common.edit")} onClick={() => setEditing(true)}><Pencil /></Button>
          )}
          <Button variant="ghost" size="icon" aria-label={t("common.delete")} disabled={remove.isPending}
            onClick={() => { if (confirm(t("eventItem.confirmDelete"))) remove.mutate(event.id) }}>
            <Trash2 />
          </Button>
        </div>
      )}
    </li>
  )
}
