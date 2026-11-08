import { ArrowRight } from "lucide-react"
import { type ReactNode } from "react"
import { Link } from "react-router"

import { EventItem } from "@/features/applications/EventItem"
import { MiniCalendar } from "@/features/applications/MiniCalendar"
import type { AgendaEvent, ApplicationListItem } from "@/features/applications/api"
import { STATUSES, statusInfo, statusLabel } from "@/features/applications/status"
import type { OverviewWidget, WidgetId } from "@/features/auth/api"
import type { Profile } from "@/features/profile/api"
import { dateLocale, t } from "@/shared/lib/i18n"
import { cn, formatDate, isoDate, scoreColor, today } from "@/shared/lib/utils"
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card"

/** What the widgets show, loaded once by the overview */
export interface OverviewData {
  applications: ApplicationListItem[]
  events: AgendaEvent[]
  profile: Profile | undefined
  aiEnabled: boolean
  /** Day selected in the calendar */
  day: string
  setDay: (day: string) => void
}

type Size = OverviewWidget["size"]

interface WidgetProps {
  data: OverviewData
  size: Size
}

// An application with no news for this many days shows up in "No news"
const WEEKS = 8

function Tile({ to, label, count, color }: { to: string; label: string; count: number; color?: string }) {
  return (
    <Link to={to} className="rounded-xl border bg-card p-4 transition-colors hover:bg-secondary/50">
      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
        {color && <span className={cn("size-2 rounded-full", color)} />}
        <span className="truncate">{label}</span>
      </p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{count}</p>
    </Link>
  )
}

function SeeAll({ to, label }: { to: string; label: string }) {
  return (
    <Link to={to} className="flex shrink-0 items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
      {label}<ArrowRight className="size-3.5" />
    </Link>
  )
}

function WidgetCard({ title, action, children, flush }: {
  title: string
  action?: ReactNode
  children: ReactNode
  /** Content without side padding, e.g. lists with dividers */
  flush?: boolean
}) {
  return (
    <Card className="h-full">
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {action}
      </CardHeader>
      <CardContent className={cn(flush && "px-0 pb-1")}>{children}</CardContent>
    </Card>
  )
}

function Empty({ children, flush }: { children: ReactNode; flush?: boolean }) {
  return <div className={cn("text-sm text-muted-foreground", flush && "px-5 pb-3")}>{children}</div>
}

/** A sentence with "{link}" replaced by a link */
function withLink(text: string, to: string, label: string) {
  return text.split("{link}").flatMap((part, i) => i === 0 ? [part]
    : [<Link key="link" to={to} className="underline">{label}</Link>, part])
}

function ApplicationRows({ items }: { items: { app: ApplicationListItem; aside: ReactNode }[] }) {
  return (
    <ul className="divide-y border-t">
      {items.map(({ app, aside }) => (
        <li key={app.id}>
          <Link to={`/applications/${app.id}`} className="flex items-center gap-3 px-5 py-2.5 hover:bg-secondary/50">
            <span className="min-w-0 flex-1 truncate text-sm">
              <span className="font-medium">{app.title ?? t("application.untitled")}</span>
              {app.company && <span className="text-muted-foreground"> · {app.company}</span>}
            </span>
            {aside}
          </Link>
        </li>
      ))}
    </ul>
  )
}

/** Widgets about reports need the AI */
function AiOff() {
  return <Empty flush>{t("ai.disabled")}</Empty>
}

// Widgets

function Counts({ data, size }: WidgetProps) {
  const { applications } = data
  return (
    <div className={cn("grid gap-3", size === "full" ? "grid-cols-2 sm:grid-cols-4 lg:grid-cols-7"
      : "grid-cols-2 sm:grid-cols-4 lg:grid-cols-3 xl:grid-cols-4")}>
      <Tile to="/applications" label={t("overview.total")} count={applications.length} />
      {STATUSES.map((s) => (
        <Tile key={s.value} to={`/applications?status=${s.value}`} label={statusLabel(s.value)} color={s.color}
          count={applications.filter((a) => a.status === s.value).length} />
      ))}
    </div>
  )
}

function Calendar({ data }: WidgetProps) {
  const dayEvents = data.events.filter((e) => e.occurred_on === data.day)
  return (
    <WidgetCard title={t("overview.calendar")}>
      <div className="space-y-3">
        <MiniCalendar events={data.events} selected={data.day} onSelect={data.setDay} />
        <div className="border-t pt-3">
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">{formatDate(data.day)}</p>
          {dayEvents.length === 0 ? <p className="text-sm text-muted-foreground">{t("calendar.noEvents")}</p> : (
            <ul className="space-y-3">{dayEvents.map((e) => <EventItem key={e.id} event={e} showApplication compact />)}</ul>
          )}
        </div>
      </div>
    </WidgetCard>
  )
}

function Events({ data }: WidgetProps) {
  // Events arrive sorted by date, so overdue ones come first
  const upcoming = data.events.filter((e) => !e.completed).slice(0, 6)
  return (
    <WidgetCard title={t("overview.events")} action={<SeeAll to="/agenda" label={t("nav.agenda")} />}>
      {upcoming.length === 0 ? <Empty>{withLink(t("overview.noEvents"), "/agenda", t("nav.agenda"))}</Empty>
        : <ul className="space-y-3">{upcoming.map((e) => <EventItem key={e.id} event={e} showApplication compact />)}</ul>}
    </WidgetCard>
  )
}

function Recent({ data }: WidgetProps) {
  const recent = [...data.applications].sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, 5)
  return (
    <WidgetCard title={t("overview.recent")} flush
      action={data.applications.length > 0 && <SeeAll to="/applications" label={t("overview.seeAll")} />}>
      {recent.length === 0 ? (
        <Empty flush>{withLink(t("overview.noApplications"), "/applications", t("nav.applications"))}</Empty>
      ) : (
        <ApplicationRows items={recent.map((app) => ({
          app,
          aside: (
            <span className="flex shrink-0 items-center gap-1.5 text-xs text-muted-foreground">
              <span className={cn("size-2 rounded-full", statusInfo(app.status).color)} />
              {statusLabel(app.status)}
            </span>
          ),
        }))} />
      )}
    </WidgetCard>
  )
}

function ProfileSummary({ data }: WidgetProps) {
  const { profile } = data
  return (
    <WidgetCard title={t("overview.profile")} action={<SeeAll to="/profile" label={t("overview.goProfile")} />}>
      <div className="text-sm text-muted-foreground">
        {!profile || profile.skills.length === 0 ? t("overview.profileEmpty") : (
          <>
            {profile.headline && <p className="font-medium text-foreground">{profile.headline}</p>}
            <p>{t("overview.profileStats", {
              skills: profile.skills.length,
              experiences: profile.experiences.length,
              projects: profile.projects.length,
            })}</p>
          </>
        )}
      </div>
    </WidgetCard>
  )
}

/** Monday of the week of a "YYYY-MM-DD" date */
function weekStart(value: string) {
  const date = new Date(`${value}T12:00:00`)
  date.setDate(date.getDate() - ((date.getDay() + 6) % 7))
  return isoDate(date)
}

function Weekly({ data }: WidgetProps) {
  const current = weekStart(today())
  const weeks = Array.from({ length: WEEKS }, (_, i) => {
    const date = new Date(`${current}T12:00:00`)
    date.setDate(date.getDate() - 7 * (WEEKS - 1 - i))
    return isoDate(date)
  })
  const counts = new Map(weeks.map((week) => [week, 0]))
  for (const app of data.applications) {
    const week = weekStart(app.applied_on ?? app.created_at.slice(0, 10))
    if (counts.has(week)) counts.set(week, counts.get(week)! + 1)
  }
  const max = Math.max(1, ...counts.values())
  const label = (week: string) => new Date(`${week}T12:00:00`).toLocaleDateString(dateLocale(), { day: "numeric", month: "short" })
  return (
    <WidgetCard title={t("overview.weekly")}
      action={<span className="text-sm text-muted-foreground">{t("overview.thisWeek", { count: counts.get(current) ?? 0 })}</span>}>
      <div className="flex h-40 items-end gap-1.5" role="img"
        aria-label={weeks.map((week) => `${label(week)}: ${counts.get(week)}`).join(", ")}>
        {weeks.map((week) => {
          const count = counts.get(week) ?? 0
          return (
            <div key={week} className="flex h-full min-w-0 flex-1 flex-col items-center justify-end gap-1">
              <span className="text-xs tabular-nums text-muted-foreground">{count > 0 ? count : ""}</span>
              <div className={cn("w-full max-w-10 rounded-t-md", week === current ? "bg-primary" : "bg-primary/25",
                count === 0 && "bg-border")} style={{ height: count === 0 ? 2 : `${(count / max) * 75}%` }} />
              <span className="w-full truncate text-center text-[11px] text-muted-foreground">{label(week)}</span>
            </div>
          )
        })}
      </div>
    </WidgetCard>
  )
}

function TopMatches({ data }: WidgetProps) {
  const top = data.applications.filter((a) => a.match_score != null)
    .sort((a, b) => b.match_score! - a.match_score!).slice(0, 5)
  return (
    <WidgetCard title={t("overview.topMatches")} flush>
      {!data.aiEnabled ? <AiOff /> : top.length === 0 ? <Empty flush>{t("overview.noReports")}</Empty> : (
        <ApplicationRows items={top.map((app) => ({
          app,
          aside: <span className={cn("shrink-0 text-sm font-semibold tabular-nums", scoreColor(app.match_score!))}>
            {app.match_score}%
          </span>,
        }))} />
      )}
    </WidgetCard>
  )
}

function StaleReports({ data }: WidgetProps) {
  const stale = data.applications.filter((a) => a.report_stale)
  return (
    <WidgetCard title={t("overview.staleReports")} flush>
      {!data.aiEnabled ? <AiOff /> : stale.length === 0 ? <Empty flush>{t("overview.noStaleReports")}</Empty> : (
        <ApplicationRows items={stale.slice(0, 6).map((app) => ({
          app,
          aside: <span className="shrink-0 text-xs text-muted-foreground">{t("overview.regenerate")}</span>,
        }))} />
      )}
    </WidgetCard>
  )
}

function MissingSkills({ data }: WidgetProps) {
  // Counted once per application, case-insensitive, shown with the first spelling met
  const found = new Map<string, { name: string; count: number }>()
  for (const app of data.applications) {
    for (const key of new Set(app.missing_skills.map((name) => name.trim().toLowerCase()))) {
      const name = app.missing_skills.find((s) => s.trim().toLowerCase() === key)!.trim()
      const entry = found.get(key) ?? { name, count: 0 }
      entry.count++
      found.set(key, entry)
    }
  }
  const skills = [...found.values()].sort((a, b) => b.count - a.count || a.name.localeCompare(b.name)).slice(0, 12)
  return (
    <WidgetCard title={t("overview.missingSkills")}>
      {!data.aiEnabled ? <Empty>{t("ai.disabled")}</Empty> : skills.length === 0 ? <Empty>{t("overview.noMissingSkills")}</Empty> : (
        <>
          <p className="mb-3 text-sm text-muted-foreground">{t("overview.missingSkillsHint")}</p>
          <ul className="flex flex-wrap gap-2">
            {skills.map((skill) => (
              <li key={skill.name} className="flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm">
                {skill.name}
                <span className="rounded-full bg-secondary px-1.5 text-xs tabular-nums text-muted-foreground">{skill.count}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </WidgetCard>
  )
}

export const WIDGETS: Record<WidgetId, { title: () => string; description: () => string; size: Size;
  render: (props: WidgetProps) => ReactNode }> = {
  counts: { title: () => t("overview.w.counts"), description: () => t("overview.w.countsHint"), size: "full", render: Counts },
  calendar: { title: () => t("overview.calendar"), description: () => t("overview.w.calendarHint"), size: "half", render: Calendar },
  events: { title: () => t("overview.events"), description: () => t("overview.w.eventsHint"), size: "half", render: Events },
  recent: { title: () => t("overview.recent"), description: () => t("overview.w.recentHint"), size: "half", render: Recent },
  profile: { title: () => t("overview.profile"), description: () => t("overview.w.profileHint"), size: "half", render: ProfileSummary },
  weekly: { title: () => t("overview.weekly"), description: () => t("overview.w.weeklyHint"), size: "half", render: Weekly },
  top_matches: { title: () => t("overview.topMatches"), description: () => t("overview.w.topMatchesHint"), size: "half", render: TopMatches },
  stale_reports: { title: () => t("overview.staleReports"), description: () => t("overview.w.staleReportsHint"), size: "half", render: StaleReports },
  missing_skills: { title: () => t("overview.missingSkills"), description: () => t("overview.w.missingSkillsHint"), size: "half", render: MissingSkills },
}

export const DEFAULT_LAYOUT: OverviewWidget[] = [
  { id: "counts", size: "full" },
  { id: "calendar", size: "half" },
  { id: "events", size: "half" },
  { id: "recent", size: "half" },
  { id: "profile", size: "half" },
]
