import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ExternalLink, Trash2 } from "lucide-react"
import { useState } from "react"
import { useNavigate, useParams } from "react-router"

import { JobPostingAssist, useJobSource } from "@/components/AiAssist"
import { ApplicationFields } from "@/components/ApplicationFields"
import { BackLink } from "@/components/BackLink"
import { EventTimeline } from "@/components/EventTimeline"
import { MatchPanel } from "@/components/MatchPanel"
import { SaveBar } from "@/components/SaveBar"
import { Button } from "@/components/ui/button"
import { Select } from "@/components/ui/input"
import { useAiFill } from "@/lib/ai"
import { api, type Application, type ApplicationChanges, isWorking } from "@/lib/api"
import { useT } from "@/lib/i18n"
import { STATUSES, statusLabel, workModeLabel } from "@/lib/status"
import { usePageTitle } from "@/lib/title"

function DetailPage({ app }: { app: Application }) {
  const t = useT()
  usePageTitle(app.title ?? t("application.untitled"))
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState<ApplicationChanges>({})
  const job = useJobSource(app.has_description ? app.id : undefined)

  const onSaved = (data: Application) => {
    queryClient.setQueryData(["application", app.id], data)
    queryClient.invalidateQueries({ queryKey: ["applications"] })
  }
  const save = useMutation({
    mutationFn: (changes: ApplicationChanges) => api.updateApplication(app.id, changes),
    onSuccess: (data) => { setDraft({}); onSaved(data) },
  })
  const remove = useMutation({
    mutationFn: () => api.deleteApplication(app.id),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["applications"] }); navigate("/applications") },
  })

  const value = <K extends keyof Application>(key: K): Application[K] =>
    (key in draft ? draft[key] : app[key]) as Application[K]
  const set = <K extends keyof Application>(key: K, v: Application[K]) => setDraft((d) => ({ ...d, [key]: v }))
  const current = { ...app, ...draft }

  const fill = useAiFill<Partial<Application>>(current, (changes, sourceText) => {
    // A new job posting (text, link or file) replaces the saved one
    const source = "application_id" in (job.source ?? {}) ? {} : { description: sourceText }
    const fromLink = job.url && !current.source_url ? { source_url: job.url } : {}
    setDraft((d) => ({ ...d, ...changes, ...source, ...fromLink }))
  })

  return (
    <div className="space-y-5 pb-20">
      <BackLink />

      <div className="flex flex-wrap items-start gap-4">
        <div className="min-w-0 flex-1">
          <h1 className="text-2xl font-semibold">{app.title ?? t("application.untitled")}</h1>
          <p className="text-muted-foreground">
            {[app.company, app.location, app.work_mode && workModeLabel(app.work_mode)].filter(Boolean).join(" · ")}
          </p>
        </div>
        <Select className="w-52" value={app.status} disabled={save.isPending} aria-label={t("list.statusLabel")}
          onChange={(e) => save.mutate({ status: e.target.value as Application["status"] })}>
          {STATUSES.map((s) => <option key={s.value} value={s.value}>{statusLabel(s.value)}</option>)}
        </Select>
        {app.source_url && (
          <a href={app.source_url} target="_blank" rel="noreferrer">
            <Button variant="outline"><ExternalLink />{t("application.posting")}</Button>
          </a>
        )}
        <Button variant="ghost" size="icon" aria-label={t("application.delete")}
          onClick={() => { if (confirm(t("application.confirmDelete"))) remove.mutate() }}>
          <Trash2 />
        </Button>
      </div>

      <div className="grid gap-5 lg:grid-cols-[1fr_380px]">
        <div className="space-y-5">
          <JobPostingAssist hint={t("application.aiHint")} job={job} fill={fill} />
          <ApplicationFields value={value} set={set} />
        </div>

        <div className="space-y-5">
          <MatchPanel application={app} />
          <EventTimeline application={app} />
        </div>
      </div>

      {Object.keys(draft).length > 0 && (
        <SaveBar message={t("common.unsaved")} saving={save.isPending} error={save.error?.message}
          onCancel={() => setDraft({})} onSave={() => save.mutate(draft)} />
      )}
    </div>
  )
}

export function ApplicationDetail() {
  const t = useT()
  const id = Number(useParams().id)
  const { data: app, error } = useQuery({
    queryKey: ["application", id],
    queryFn: () => api.getApplication(id),
    refetchInterval: (q) => (isWorking(q.state.data?.advice_status) ? 3000 : false),
  })
  if (error) return <p className="text-sm text-red-600 dark:text-red-400">{(error as Error).message}</p>
  if (!app) return <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
  return <DetailPage key={app.id} app={app} />
}
