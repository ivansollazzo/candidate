import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { useNavigate } from "react-router"

import { JobPostingAssist, useJobSource } from "@/components/AiAssist"
import { ApplicationFields } from "@/components/ApplicationFields"
import { BackLink } from "@/components/BackLink"
import { SaveBar } from "@/components/SaveBar"
import { useAiFill, useAiStatus } from "@/lib/ai"
import { api, type Application, type ApplicationChanges } from "@/lib/api"
import { useT } from "@/lib/i18n"
import { usePageTitle } from "@/lib/title"
import { today } from "@/lib/utils"

const EMPTY: Partial<Application> = {
  applied_on: today(),
  skills: [],
  requirements: [],
  nice_to_have: [],
  responsibilities: [],
  benefits: [],
  languages: [],
}

export function NewApplication() {
  const t = useT()
  usePageTitle(t("new.title"))
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState<Partial<Application>>(EMPTY)
  const [description, setDescription] = useState<string | null>(null)
  const job = useJobSource()
  const ai = useAiStatus()

  const value = <K extends keyof Application>(key: K) => draft[key] as Application[K]
  const set = <K extends keyof Application>(key: K, v: Application[K]) => setDraft((d) => ({ ...d, [key]: v }))

  const fill = useAiFill(draft, (changes, sourceText) => {
    const fromLink = job.url && !draft.source_url ? { source_url: job.url } : {}
    setDraft((d) => ({ ...d, ...changes, ...fromLink }))
    setDescription(sourceText)
  })
  const create = useMutation({
    mutationFn: (fields: ApplicationChanges) => api.createApplication(fields),
    onSuccess: (app) => {
      queryClient.invalidateQueries({ queryKey: ["applications"] })
      navigate(`/applications/${app.id}`)
    },
  })
  const hasTitle = !!draft.title?.trim()

  return (
    <div className="mx-auto max-w-4xl space-y-5 pb-20">
      <BackLink />
      <div>
        <h1 className="text-xl font-semibold">{t("new.title")}</h1>
        <p className="text-sm text-muted-foreground">
          {ai.enabled ? t("new.introAi") : t("new.intro")}
        </p>
      </div>

      <JobPostingAssist hint={t("new.aiHint")} job={job} fill={fill} />

      <ApplicationFields value={value} set={set} />

      <SaveBar message={hasTitle ? t("new.unsaved") : t("new.needTitle")}
        saving={create.isPending} error={create.error?.message} disabled={!hasTitle} saveLabel={t("new.save")}
        onSave={() => create.mutate({ ...draft, description })} />
    </div>
  )
}
