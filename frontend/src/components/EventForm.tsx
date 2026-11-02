import { Loader2, Save } from "lucide-react"
import { useState } from "react"

import { Button } from "@/components/ui/button"
import { Input, Label, Select, Textarea } from "@/components/ui/input"
import type { ApplicationSummary, EventFields } from "@/lib/api"
import { addMinutes, SCHEDULABLE_TYPES } from "@/lib/events"
import { useT } from "@/lib/i18n"
import { eventLabel } from "@/lib/status"
import { cn, today } from "@/lib/utils"

// Shortcuts that set the end time from the start time
const DURATIONS = [
  { minutes: 30, label: "30 min" },
  { minutes: 60, label: "1 h" },
  { minutes: 90, label: "1 h 30" },
  { minutes: 120, label: "2 h" },
]

/**
 * Create/edit form for an event. With `applications` the application is picked in the form (agenda);
 * without it, the application comes from `initial` (detail view).
 */
export function EventForm({ initial, applications, saving, error, onSubmit, onCancel }: {
  initial?: Partial<EventFields>
  applications?: ApplicationSummary[]
  saving: boolean
  error?: string | null
  onSubmit: (fields: EventFields) => void
  onCancel?: () => void
}) {
  const t = useT()
  const [form, setForm] = useState({
    application_id: initial?.application_id ?? 0,
    type: initial?.type ?? "interview",
    occurred_on: initial?.occurred_on ?? today(),
    starts_at: initial?.starts_at?.slice(0, 5) ?? "",
    ends_at: initial?.ends_at?.slice(0, 5) ?? "",
    title: initial?.title ?? "",
    details: initial?.details ?? "",
    completed: initial?.completed ?? false,
  })
  const set = (changes: Partial<typeof form>) => setForm({ ...form, ...changes })
  // The end time is optional and only makes sense after a start time ("HH:MM" strings compare in order)
  const endInvalid = form.ends_at !== "" && (form.starts_at === "" || form.ends_at <= form.starts_at)
  const valid = form.application_id > 0 && form.title.trim() !== "" && form.occurred_on !== "" && !endInvalid

  return (
    <form className="space-y-3" onSubmit={(e) => {
      e.preventDefault()
      if (valid) onSubmit({
        ...form, title: form.title.trim(), starts_at: form.starts_at || null,
        ends_at: (form.starts_at && form.ends_at) || null, details: form.details || null,
      })
    }}>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-[1fr_1fr_130px_130px]">
        {applications && (
          <div className="col-span-2 sm:col-span-4">
            <Label className="mb-1 block">{t("eventForm.application")}</Label>
            <Select value={form.application_id} onChange={(e) => set({ application_id: Number(e.target.value) })}>
              <option value={0} disabled>{t("eventForm.chooseApplication")}</option>
              {applications.map((a) => (
                <option key={a.id} value={a.id}>
                  {[a.title ?? t("application.untitled"), a.company].filter(Boolean).join(" · ")}
                </option>
              ))}
            </Select>
          </div>
        )}
        <div>
          <Label className="mb-1 block">{t("eventForm.type")}</Label>
          <Select value={form.type} onChange={(e) => set({ type: e.target.value })}>
            {SCHEDULABLE_TYPES.map((type) => <option key={type} value={type}>{eventLabel(type)}</option>)}
          </Select>
        </div>
        <div>
          <Label className="mb-1 block">{t("eventForm.date")}</Label>
          <Input type="date" required value={form.occurred_on} onChange={(e) => set({ occurred_on: e.target.value })} />
        </div>
        <div>
          <Label className="mb-1 block">{t("eventForm.time")}</Label>
          <Input type="time" value={form.starts_at}
            onChange={(e) => set({ starts_at: e.target.value, ...(e.target.value ? {} : { ends_at: "" }) })} />
        </div>
        <div>
          <Label className="mb-1 block">{t("eventForm.end")}</Label>
          <Input type="time" value={form.ends_at} disabled={!form.starts_at} aria-invalid={endInvalid}
            className={cn(endInvalid && "border-red-500 focus-visible:ring-red-500/40")}
            onChange={(e) => set({ ends_at: e.target.value })} />
        </div>
      </div>
      {form.starts_at && (
        <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
          <span>{t("eventForm.duration")}</span>
          {DURATIONS.map(({ minutes, label }) => {
            const end = addMinutes(form.starts_at, minutes)
            return end && (
              <button key={minutes} type="button" onClick={() => set({ ends_at: end })}
                className={cn("rounded-full border px-2.5 py-0.5 transition-colors hover:bg-accent hover:text-foreground",
                  form.ends_at === end && "border-primary bg-primary text-primary-foreground hover:bg-primary hover:text-primary-foreground")}>
                {label}
              </button>
            )
          })}
          {endInvalid && <span className="text-red-600 dark:text-red-400">{t("eventForm.endInvalid")}</span>}
        </div>
      )}
      <div>
        <Label className="mb-1 block">{t("eventForm.title")}</Label>
        <Input placeholder={t("events.titlePlaceholder")} value={form.title} onChange={(e) => set({ title: e.target.value })} />
      </div>
      <div>
        <Label className="mb-1 block">{t("eventForm.details")}</Label>
        <Textarea placeholder={t("events.detailsPlaceholder")} value={form.details}
          onChange={(e) => set({ details: e.target.value })} />
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={form.completed} onChange={(e) => set({ completed: e.target.checked })} />
          {t("eventForm.completed")}
        </label>
        {error && <span className="text-sm text-red-600 dark:text-red-400">{error}</span>}
        <div className="ml-auto flex gap-2">
          {onCancel && <Button type="button" variant="ghost" size="sm" onClick={onCancel}>{t("common.cancel")}</Button>}
          <Button type="submit" size="sm" disabled={!valid || saving}>
            {saving ? <Loader2 className="animate-spin" /> : <Save />}{t("eventForm.save")}
          </Button>
        </div>
      </div>
    </form>
  )
}
