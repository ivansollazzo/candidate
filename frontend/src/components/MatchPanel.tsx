import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { CheckCircle2, CircleAlert, CircleDashed, Loader2, Sparkles } from "lucide-react"
import { Link } from "react-router"

import { ErrorText } from "@/components/ErrorText"
import { SkillLevelDots } from "@/components/SkillLevelDots"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useAiStatus } from "@/lib/ai"
import { api, type Application, isWorking, type SkillMatchItem } from "@/lib/api"
import { useT } from "@/lib/i18n"
import { cn } from "@/lib/utils"

function SkillRow({ item }: { item: SkillMatchItem }) {
  const t = useT()
  const Icon = item.status === "match" ? CheckCircle2 : item.status === "partial" ? CircleDashed : CircleAlert
  const color = item.status === "match" ? "text-emerald-600 dark:text-emerald-400" : item.status === "partial" ? "text-amber-600 dark:text-amber-400" : "text-red-600 dark:text-red-400"
  return (
    <li className="flex items-start gap-2 text-sm">
      <Icon className={cn("mt-0.5 size-4 shrink-0", color)} />
      <span>
        {item.skill}
        {item.importance === "nice_to_have" && <span className="text-muted-foreground"> ({t("importance.nice_to_have")})</span>}
        {item.matched_with && item.matched_with !== item.skill && (
          <span className="text-muted-foreground"> ↔ {item.matched_with}</span>
        )}
        {item.note && <span className="block text-xs text-muted-foreground">{item.note}</span>}
      </span>
      {item.level != null && <SkillLevelDots level={item.level} className="ml-auto shrink-0" />}
    </li>
  )
}

export function MatchPanel({ application }: { application: Application }) {
  const t = useT()
  const queryClient = useQueryClient()
  const match = useQuery({
    queryKey: ["match", application.id, application.skills],
    queryFn: () => api.getMatch(application.id),
    enabled: application.skills.length > 0,
    // Recomputed every time the application is opened: the profile may have changed meanwhile
    gcTime: 0,
    refetchOnMount: "always",
  })
  const advice = useMutation({
    mutationFn: () => api.requestAdvice(application.id),
    onSuccess: (data) => queryClient.setQueryData(["application", application.id], data),
  })
  const ai = useAiStatus()
  const data = match.data
  const adviceRunning = isWorking(application.advice_status)

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("match.title")}</CardTitle>
        {data && data.has_profile && (
          <span className={cn("text-2xl font-semibold tabular-nums",
            data.score >= 70 ? "text-emerald-600 dark:text-emerald-400" : data.score >= 40 ? "text-amber-600 dark:text-amber-400" : "text-red-600 dark:text-red-400")}>
            {data.score}%
          </span>
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        {application.skills.length === 0 && (
          <p className="text-sm text-muted-foreground">{t("match.addSkills")}</p>
        )}
        {match.isLoading && <p className="text-sm text-muted-foreground">{t("match.computing")}</p>}
        {data && !data.has_profile && (
          <p className="text-sm text-muted-foreground">
            {t("match.noProfile").split("{link}").flatMap((part, i) => i === 0 ? [part]
              : [<Link key="link" to="/profile" className="underline">{t("match.profileLink")}</Link>, part])}
          </p>
        )}
        {data && data.has_profile && (
          <>
            {data.score > 0 && (
              <div className="h-2 overflow-hidden rounded-full bg-secondary">
                <div className="h-full bg-emerald-500" style={{ width: `${data.score}%` }} />
              </div>
            )}
            {[
              { title: t("match.matched"), items: data.matched },
              { title: t("match.partial"), items: data.partial },
              { title: t("match.missing"), items: data.missing },
            ].filter((g) => g.items.length > 0).map((group) => (
              <div key={group.title}>
                <h4 className="mb-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  {group.title} ({group.items.length})
                </h4>
                <ul className="space-y-1">{group.items.map((i) => <SkillRow key={i.skill} item={i} />)}</ul>
              </div>
            ))}
          </>
        )}

        {ai.enabled && <div className="border-t pt-4">
          <div className="mb-2 flex items-center justify-between">
            <h4 className="text-sm font-medium">{t("match.advice")}</h4>
            <Button size="sm" variant="outline" disabled={adviceRunning || advice.isPending || !data?.has_profile || !ai.ready}
              title={ai.reason ?? undefined}
              onClick={() => advice.mutate()}>
              {adviceRunning ? <Loader2 className="animate-spin" /> : <Sparkles />}
              {application.advice ? t("match.regenerate") : t("match.generate")}
            </Button>
          </div>
          {adviceRunning && <p className="text-sm text-muted-foreground">{t("match.adviceRunning")}</p>}
          {!ai.ready && !adviceRunning && <p className="text-sm text-muted-foreground">{ai.reason}</p>}
          {!adviceRunning && <ErrorText error={application.advice?.error} />}
          {!adviceRunning && application.advice?.summary && (
            <div className="space-y-3 text-sm">
              <p>{application.advice.summary}</p>
              {!!application.advice.strengths?.length && (
                <ul className="list-disc space-y-0.5 pl-5">
                  {application.advice.strengths.map((s) => <li key={s}>{s}</li>)}
                </ul>
              )}
              {!!application.advice.improvements?.length && (
                <ul className="space-y-2">
                  {application.advice.improvements.map((i) => (
                    <li key={i.skill} className="rounded-md bg-secondary p-2.5">
                      <span className="font-medium">{i.skill}</span>
                      <p className="text-muted-foreground">{i.suggestion}</p>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>}
      </CardContent>
    </Card>
  )
}
