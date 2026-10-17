import { Plus } from "lucide-react"
import { useState } from "react"

import { EventForm } from "@/components/EventForm"
import { EventItem } from "@/components/EventItem"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import type { Application } from "@/lib/api"
import { useEventMutations } from "@/lib/events"
import { useT } from "@/lib/i18n"

/** Application events: upcoming ones and the history, status changes included. */
export function EventTimeline({ application }: { application: Application }) {
  const t = useT()
  const { add } = useEventMutations()
  const [adding, setAdding] = useState(false)
  const events = [...application.events].sort((a, b) => b.occurred_on.localeCompare(a.occurred_on) || b.id - a.id)

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("events.title")}</CardTitle>
        {!adding && <Button variant="outline" size="sm" onClick={() => setAdding(true)}><Plus />{t("agenda.new")}</Button>}
      </CardHeader>
      <CardContent className="space-y-4">
        {adding && (
          <div className="rounded-lg border bg-secondary/40 p-3">
            <EventForm initial={{ application_id: application.id }} saving={add.isPending} error={add.error?.message}
              onCancel={() => setAdding(false)} onSubmit={(fields) => add.mutate(fields, { onSuccess: () => setAdding(false) })} />
          </div>
        )}
        <ul className="space-y-3">
          {events.length === 0 && <li className="text-sm text-muted-foreground">{t("events.empty")}</li>}
          {events.map((event) => <EventItem key={event.id} event={event} />)}
        </ul>
      </CardContent>
    </Card>
  )
}
