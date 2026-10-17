import { ChevronLeft, ChevronRight } from "lucide-react"
import { useState } from "react"

import { Button } from "@/components/ui/button"
import type { AgendaEvent } from "@/lib/api"
import { isOverdue } from "@/lib/events"
import { dateLocale, useT } from "@/lib/i18n"
import { cn, isoDate, today } from "@/lib/utils"

/** Month calendar with a dot on days that have events; a day can be selected. */
export function MiniCalendar({ events, selected, onSelect }: {
  events: AgendaEvent[]
  selected: string
  onSelect: (day: string) => void
}) {
  const t = useT()
  const [month, setMonth] = useState(() => {
    const [y, m] = selected.split("-").map(Number)
    return new Date(y, m - 1, 1)
  })
  const byDay = new Map<string, AgendaEvent[]>()
  for (const event of events) byDay.set(event.occurred_on, [...(byDay.get(event.occurred_on) ?? []), event])
  // Weeks start on Monday; days before the 1st are left blank
  const offset = (month.getDay() + 6) % 7
  const daysInMonth = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate()
  const days = Array.from({ length: daysInMonth }, (_, i) => isoDate(new Date(month.getFullYear(), month.getMonth(), i + 1)))
  const weekdays = Array.from({ length: 7 }, (_, i) =>
    new Date(2024, 0, 1 + i).toLocaleDateString(dateLocale(), { weekday: "narrow" })) // 2024-01-01 is a Monday
  const shift = (delta: number) => setMonth(new Date(month.getFullYear(), month.getMonth() + delta, 1))
  const now = today()

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-1">
        <span className="flex-1 text-sm font-medium capitalize">
          {month.toLocaleDateString(dateLocale(), { month: "long", year: "numeric" })}
        </span>
        <Button variant="ghost" size="sm" onClick={() => {
          const d = new Date()
          setMonth(new Date(d.getFullYear(), d.getMonth(), 1))
          onSelect(now)
        }}>{t("calendar.today")}</Button>
        <Button variant="ghost" size="icon" aria-label={t("calendar.previous")} onClick={() => shift(-1)}><ChevronLeft /></Button>
        <Button variant="ghost" size="icon" aria-label={t("calendar.next")} onClick={() => shift(1)}><ChevronRight /></Button>
      </div>
      <div className="grid grid-cols-7 gap-0.5 text-center text-xs">
        {weekdays.map((d, i) => <span key={i} className="py-1 text-muted-foreground">{d}</span>)}
        {Array.from({ length: offset }, (_, i) => <span key={`empty-${i}`} />)}
        {days.map((day) => {
          const dayEvents = byDay.get(day) ?? []
          const pending = dayEvents.filter((e) => !e.completed)
          const dot = pending.some(isOverdue) ? "bg-red-500" : pending.length > 0 ? "bg-blue-500" : dayEvents.length > 0 ? "bg-muted-foreground/40" : null
          return (
            <button key={day} type="button" onClick={() => onSelect(day)} aria-pressed={day === selected}
              className={cn("flex h-9 flex-col items-center justify-center rounded-md text-sm tabular-nums hover:bg-secondary",
                day === now && "font-semibold ring-1 ring-ring",
                day === selected && "bg-foreground text-background hover:bg-foreground/90")}>
              {Number(day.slice(8))}
              <span className={cn("size-1 rounded-full", dot ?? "invisible")} />
            </button>
          )
        })}
      </div>
    </div>
  )
}
