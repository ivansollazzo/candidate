import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ExternalLink, Trash2 } from "lucide-react"
import { useState } from "react"
import { useNavigate, useParams } from "react-router"

import { ApplicationFields } from "@/features/applications/ApplicationFields"
import { Attachments } from "@/features/applications/Attachments"
import { EventTimeline } from "@/features/applications/EventTimeline"
import { type Application, type ApplicationChanges, applicationsApi } from "@/features/applications/api"
import { STATUSES, statusLabel, workModeLabel } from "@/features/applications/status"
import { AiAssist, ProposalCard, useJobSource } from "@/features/background_jobs/AiAssist"
import { findJob, useJobs } from "@/features/background_jobs/hooks"
import { ReportPanel } from "@/features/reports/ReportPanel"
import { BackLink } from "@/shared/components/BackLink"
import { ErrorText } from "@/shared/components/ErrorText"
import { SaveBar } from "@/shared/components/SaveBar"
import { isWorking } from "@/shared/lib/http"
import { useT } from "@/shared/lib/i18n"
import { usePageTitle } from "@/shared/lib/title"
import { Button } from "@/shared/ui/button"
import { Select } from "@/shared/ui/input"

function DetailPage({ app }: { app: Application }) {
  const t = useT()
  usePageTitle(app.title ?? t("application.untitled"))
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState<ApplicationChanges>({})
  const source = useJobSource(app.has_description)
  const { data: jobs } = useJobs()
  const fillJob = findJob(jobs, "application", app.id)

  const onSaved = (data: Application) => {
    queryClient.setQueryData(["application", app.id], data)
    queryClient.invalidateQueries({ queryKey: ["applications"] })
  }
  const save = useMutation({
    mutationFn: (changes: ApplicationChanges) => applicationsApi.updateApplication(app.id, changes),
    onSuccess: (data) => { setDraft({}); onSaved(data) },
  })
  const remove = useMutation({
    mutationFn: () => applicationsApi.deleteApplication(app.id),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["applications"] }); navigate("/applications") },
  })

  const value = <K extends keyof Application>(key: K): Application[K] =>
    (key in draft ? draft[key] : app[key]) as Application[K]
  const set = <K extends keyof Application>(key: K, v: Application[K]) => setDraft((d) => ({ ...d, [key]: v }))
  // A new job posting (text, link or file) replaces the saved one when the job is done
  const fill = async () => {
    await applicationsApi.fillApplication(app.id, source.source ?? undefined)
    source.reset()
  }

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
          {fillJob && <ProposalCard job={fillJob} />}
          <AiAssist hint={t("application.aiHint")} runLabel={t("application.aiRun")} job={fillJob}
            canRun={source.source !== null} onRun={fill}>
            {source.input}
          </AiAssist>
          <ApplicationFields value={value} set={set} />
          <Attachments application={app} />
        </div>

        <div className="space-y-5">
          <ReportPanel application={app} />
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
    queryFn: () => applicationsApi.getApplication(id),
    refetchInterval: (q) => (isWorking(q.state.data?.report_status) ? 3000 : false),
  })
  if (error) return <ErrorText error={error} />
  if (!app) return <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
  return <DetailPage key={app.id} app={app} />
}
