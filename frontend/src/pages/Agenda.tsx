import { useQuery } from "@tanstack/react-query"
import { Plus } from "lucide-react"
import { type ReactNode, useState } from "react"

import { EventForm } from "@/components/EventForm"
import { EventItem } from "@/components/EventItem"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { api } from "@/lib/api"
import { isOverdue, useEventMutations } from "@/lib/events"
import { useT } from "@/lib/i18n"
import { usePageTitle } from "@/lib/title"

function Section({ title, count, children }: { title: string; count: number; children: ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title} <span className="font-normal text-muted-foreground">{count}</span></CardTitle>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  )
}

/** All application events: overdue, upcoming and completed. */
export function Agenda() {
  const t = useT()
  usePageTitle(t("nav.agenda"))
  const [adding, setAdding] = useState(false)
  const { add } = useEventMutations()
  const { data: events = [], isLoading, error } = useQuery({ queryKey: ["events"], queryFn: api.listEvents })
  const { data: applications = [] } = useQuery({ queryKey: ["applications"], queryFn: api.listApplications })

  const overdue = events.filter(isOverdue)
  const upcoming = events.filter((e) => !e.completed && !isOverdue(e))
  const completed = events.filter((e) => e.completed).reverse()

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex-1">
          <h1 className="text-xl font-semibold">{t("nav.agenda")}</h1>
          <p className="text-sm text-muted-foreground">{t("agenda.intro")}</p>
        </div>
        {!adding && (
          <Button onClick={() => setAdding(true)} disabled={applications.length === 0}
            title={applications.length === 0 ? t("agenda.noApplications") : undefined}>
            <Plus />{t("agenda.new")}
          </Button>
        )}
      </div>

      {adding && (
        <Card>
          <CardHeader><CardTitle>{t("agenda.new")}</CardTitle></CardHeader>
          <CardContent>
            <EventForm applications={applications} saving={add.isPending} error={add.error?.message}
              onCancel={() => setAdding(false)} onSubmit={(fields) => add.mutate(fields, { onSuccess: () => setAdding(false) })} />
          </CardContent>
        </Card>
      )}

      {error && <p className="text-sm text-red-600 dark:text-red-400">{(error as Error).message}</p>}
      {isLoading ? <p className="text-sm text-muted-foreground">{t("common.loading")}</p> : (
        <>
          {overdue.length > 0 && (
            <Section title={t("agenda.overdue")} count={overdue.length}>
              <ul className="space-y-4">{overdue.map((e) => <EventItem key={e.id} event={e} showApplication />)}</ul>
            </Section>
          )}
          <Section title={t("agenda.upcoming")} count={upcoming.length}>
            {upcoming.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                {applications.length === 0 ? t("agenda.noApplications") : t("agenda.empty")}
              </p>
            ) : <ul className="space-y-4">{upcoming.map((e) => <EventItem key={e.id} event={e} showApplication />)}</ul>}
          </Section>
          <Section title={t("agenda.completed")} count={completed.length}>
            {completed.length === 0 ? <p className="text-sm text-muted-foreground">{t("agenda.noCompleted")}</p>
              : <ul className="space-y-4">{completed.map((e) => <EventItem key={e.id} event={e} showApplication />)}</ul>}
          </Section>
        </>
      )}
    </div>
  )
}
