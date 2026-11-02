import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { useNavigate } from "react-router"

import { AiAssist, useJobSource } from "@/components/AiAssist"
import { ApplicationFields } from "@/components/ApplicationFields"
import { BackLink } from "@/components/BackLink"
import { SaveBar } from "@/components/SaveBar"
import { useAiStatus } from "@/lib/ai"
import { api, type Application, type ApplicationChanges } from "@/lib/api"
import { useCurrentUser, useSavePreference } from "@/lib/auth"
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
  const job = useJobSource()
  // Whether to also generate the compatibility report: a preference of the user
  const withReport = useCurrentUser()?.report_after_fill ?? false
  const savePreference = useSavePreference()
  const ai = useAiStatus()

  const value = <K extends keyof Application>(key: K) => draft[key] as Application[K]
  const set = <K extends keyof Application>(key: K, v: Application[K]) => setDraft((d) => ({ ...d, [key]: v }))

  const create = useMutation({
    mutationFn: (fields: ApplicationChanges) => api.createApplication(fields),
    onSuccess: (app) => {
      queryClient.invalidateQueries({ queryKey: ["applications"] })
      navigate(`/applications/${app.id}`)
    },
  })
  // Saved at once with its posting: the AI fills it in the background, shown in the list meanwhile
  const createWithAi = async () => {
    await api.createApplicationWithAi(job.source!, withReport)
    queryClient.invalidateQueries({ queryKey: ["applications"] })
    navigate("/applications")
  }
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

      <AiAssist hint={t("new.aiHint")} runLabel={t("new.createWithAi")} job={undefined}
        canRun={job.source != null} onRun={createWithAi}>
        {job.input}
        <label className="flex items-start gap-2 text-sm">
          <input type="checkbox" className="mt-0.5 size-4 cursor-pointer accent-primary" checked={withReport}
            onChange={(e) => savePreference({ report_after_fill: e.target.checked })} />
          <span>
            {t("new.withReport")}
            <span className="block text-xs text-muted-foreground">{t("new.withReportHint")}</span>
          </span>
        </label>
      </AiAssist>

      {ai.enabled && <h2 className="pt-2 text-sm font-medium text-muted-foreground">{t("new.manual")}</h2>}
      <ApplicationFields value={value} set={set} />

      <SaveBar message={hasTitle ? t("new.unsaved") : t("new.needTitle")}
        saving={create.isPending} error={create.error?.message} disabled={!hasTitle} saveLabel={t("new.save")}
        onSave={() => create.mutate(draft)} />
    </div>
  )
}
