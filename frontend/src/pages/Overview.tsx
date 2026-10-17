import { useQuery } from "@tanstack/react-query"
import { ArrowRight } from "lucide-react"
import { type ReactNode, useState } from "react"
import { Link } from "react-router"

import { EventItem } from "@/components/EventItem"
import { MiniCalendar } from "@/components/MiniCalendar"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { api, type ApplicationSummary } from "@/lib/api"
import { t, useT } from "@/lib/i18n"
import { STATUSES, statusInfo, statusLabel } from "@/lib/status"
import { usePageTitle } from "@/lib/title"
import { cn, formatDate, today } from "@/lib/utils"

function Tile({ to, label, count, color }: { to: string; label: string; count: number; color?: string }) {
  return (
    <Link to={to} className="rounded-xl border bg-card p-4 transition-colors hover:bg-secondary/50">
      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
        {color && <span className={cn("size-2 rounded-full", color)} />}
        {label}
      </p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{count}</p>
    </Link>
  )
}

function ApplicationLink({ app, aside }: { app: ApplicationSummary; aside: ReactNode }) {
  return (
    <li>
      <Link to={`/applications/${app.id}`} className="flex items-center gap-3 px-4 py-2.5 hover:bg-secondary/50">
        <span className="min-w-0 flex-1 truncate text-sm">
          <span className="font-medium">{app.title ?? t("application.untitled")}</span>
          {app.company && <span className="text-muted-foreground"> · {app.company}</span>}
        </span>
        {aside}
      </Link>
    </li>
  )
}

function SeeAll({ to, label }: { to: string; label: string }) {
  return (
    <Link to={to} className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
      {label}<ArrowRight className="size-3.5" />
    </Link>
  )
}

export function Overview() {
  useT()
  usePageTitle(t("overview.title"))
  const { data: applications = [], isLoading, error } = useQuery({ queryKey: ["applications"], queryFn: api.listApplications })
  const { data: profile } = useQuery({ queryKey: ["profile"], queryFn: api.getProfile })
  const { data: events = [] } = useQuery({ queryKey: ["events"], queryFn: api.listEvents })
  const [day, setDay] = useState(today)

  // Events arrive sorted by date, so overdue ones come first
  const upcoming = events.filter((e) => !e.completed).slice(0, 6)
  const dayEvents = events.filter((e) => e.occurred_on === day)
  const recent = [...applications].sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, 5)
  const firstName = profile?.full_name?.split(" ")[0]

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold">{t("overview.title")}</h1>
        <p className="text-sm text-muted-foreground">
          {firstName ? t("overview.greeting", { name: firstName }) : t("overview.intro")}
        </p>
      </div>

      {error && <p className="text-sm text-red-600 dark:text-red-400">{(error as Error).message}</p>}
      {isLoading ? <p className="text-sm text-muted-foreground">{t("common.loading")}</p> : (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
            <Tile to="/applications" label={t("overview.total")} count={applications.length} />
            {STATUSES.map((s) => (
              <Tile key={s.value} to={`/applications?status=${s.value}`} label={statusLabel(s.value)} color={s.color}
                count={applications.filter((a) => a.status === s.value).length} />
            ))}
          </div>

          <div className="grid gap-5 lg:grid-cols-2">
            <Card>
              <CardHeader><CardTitle>{t("overview.calendar")}</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                <MiniCalendar events={events} selected={day} onSelect={setDay} />
                <div className="border-t pt-3">
                  <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">{formatDate(day)}</p>
                  {dayEvents.length === 0 ? <p className="text-sm text-muted-foreground">{t("calendar.noEvents")}</p> : (
                    <ul className="space-y-3">{dayEvents.map((e) => <EventItem key={e.id} event={e} showApplication compact />)}</ul>
                  )}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>{t("overview.events")}</CardTitle>
                <SeeAll to="/agenda" label={t("nav.agenda")} />
              </CardHeader>
              <CardContent>
                {upcoming.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    {t("overview.noEvents").split("{link}").flatMap((part, i) => i === 0 ? [part]
                      : [<Link key="link" to="/agenda" className="underline">{t("nav.agenda")}</Link>, part])}
                  </p>
                ) : <ul className="space-y-3">{upcoming.map((e) => <EventItem key={e.id} event={e} showApplication compact />)}</ul>}
              </CardContent>
            </Card>
          </div>

          <div className="grid gap-5 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>{t("overview.recent")}</CardTitle>
                {applications.length > 0 && <SeeAll to="/applications" label={t("overview.seeAll")} />}
              </CardHeader>
              <CardContent className="px-0 pb-1">
                {recent.length === 0 ? (
                  <div className="px-4 text-sm text-muted-foreground">
                    {t("overview.noApplications").split("{link}").flatMap((part, i) => i === 0 ? [part]
                      : [<Link key="link" to="/applications" className="underline">{t("nav.applications")}</Link>, part])}
                  </div>
                ) : (
                  <ul className="divide-y border-t">
                    {recent.map((app) => (
                      <ApplicationLink key={app.id} app={app} aside={
                        <span className="flex shrink-0 items-center gap-1.5 text-xs text-muted-foreground">
                          <span className={cn("size-2 rounded-full", statusInfo(app.status).color)} />
                          {statusLabel(app.status)}
                        </span>
                      } />
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>

            {profile && (
              <Card className="self-start">
                <CardHeader>
                  <CardTitle>{t("overview.profile")}</CardTitle>
                  <SeeAll to="/profile" label={t("overview.goProfile")} />
                </CardHeader>
                <CardContent className="text-sm text-muted-foreground">
                  {profile.skills.length === 0 ? t("overview.profileEmpty") : (
                    <>
                      {profile.headline && <p className="font-medium text-foreground">{profile.headline}</p>}
                      <p>{t("overview.profileStats", {
                        skills: profile.skills.length,
                        experiences: profile.experiences.length,
                        projects: profile.projects.length,
                      })}</p>
                    </>
                  )}
                </CardContent>
              </Card>
            )}
          </div>
        </>
      )}
    </div>
  )
}
