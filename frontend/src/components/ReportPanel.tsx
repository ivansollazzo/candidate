import { useMutation, useQueryClient } from "@tanstack/react-query"
import { CheckCircle2, CircleAlert, CircleDashed, Loader2, Sparkles, TriangleAlert } from "lucide-react"

import { ErrorText } from "@/components/ErrorText"
import { SkillLevelDots } from "@/components/SkillLevelDots"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useAiStatus } from "@/lib/ai"
import { api, type Application, isWorking, type ReportSkill } from "@/lib/api"
import { useT } from "@/lib/i18n"
import { cn } from "@/lib/utils"

function SkillRow({ item }: { item: ReportSkill }) {
  const t = useT()
  const Icon = item.status === "match" ? CheckCircle2 : item.status === "partial" ? CircleDashed : CircleAlert
  const color = item.status === "match" ? "text-emerald-600 dark:text-emerald-400" : item.status === "partial" ? "text-amber-600 dark:text-amber-400" : "text-red-600 dark:text-red-400"
  return (
    <li className="flex items-start gap-2 text-sm">
      <Icon className={cn("mt-0.5 size-4 shrink-0", color)} />
      <span className="min-w-0">
        {item.skill}
        {item.importance === "nice_to_have" && <span className="text-muted-foreground"> ({t("importance.nice_to_have")})</span>}
        {item.matched_with && item.matched_with !== item.skill && (
          <span className="text-muted-foreground"> ↔ {item.matched_with}</span>
        )}
        {item.reason && <span className="block text-xs text-muted-foreground">{item.reason}</span>}
        {item.note && <span className="block text-xs text-muted-foreground">{item.note}</span>}
      </span>
      {item.level != null && <SkillLevelDots level={item.level} className="ml-auto shrink-0" />}
    </li>
  )
}

/**
 * Compatibility report and advice, generated on request by the local model. Shown only with AI on:
 * turning AI off deletes the reports.
 */
export function ReportPanel({ application }: { application: Application }) {
  const t = useT()
  const queryClient = useQueryClient()
  const ai = useAiStatus()
  const generate = useMutation({
    mutationFn: () => api.requestReport(application.id),
    onSuccess: (data) => queryClient.setQueryData(["application", application.id], data),
  })
  if (!ai.enabled) return null

  const report = application.report
  const running = isWorking(application.report_status)
  const done = application.report_status === "done" && report?.skills ? report : null
  const skills = done?.skills ?? []
  const scored = skills.filter((s) => s.kind !== "soft")
  const score = done?.score ?? 0

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("match.title")}</CardTitle>
        {done && (
          <span className={cn("text-2xl font-semibold tabular-nums",
            score >= 70 ? "text-emerald-600 dark:text-emerald-400" : score >= 40 ? "text-amber-600 dark:text-amber-400" : "text-red-600 dark:text-red-400")}>
            {score}%
          </span>
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        {done && application.report_stale && !running && (
          <p className="flex gap-2 rounded-md bg-amber-500/10 p-2.5 text-sm text-amber-700 dark:text-amber-300">
            <TriangleAlert className="mt-0.5 size-4 shrink-0" />{t("report.stale")}
          </p>
        )}
        {!done && !running && (
          <p className="text-sm text-muted-foreground">
            {application.skills.length === 0 ? t("match.addSkills") : t("report.intro")}
          </p>
        )}
        {running && (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />{t("report.running")}
          </p>
        )}
        {application.report_status === "failed" && !running && <ErrorText error={report?.error} />}

        {done && (
          <>
            {score > 0 && (
              <div className="h-2 overflow-hidden rounded-full bg-secondary">
                <div className="h-full bg-emerald-500" style={{ width: `${score}%` }} />
              </div>
            )}
            {[
              { title: t("match.matched"), items: scored.filter((s) => s.status === "match") },
              { title: t("match.partial"), items: scored.filter((s) => s.status === "partial") },
              { title: t("match.missing"), items: scored.filter((s) => s.status === "missing") },
              { title: t("match.soft"), items: skills.filter((s) => s.kind === "soft") },
            ].filter((g) => g.items.length > 0).map((group) => (
              <div key={group.title}>
                <h4 className="mb-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  {group.title} ({group.items.length})
                </h4>
                <ul className="space-y-1.5">{group.items.map((i) => <SkillRow key={i.skill} item={i} />)}</ul>
              </div>
            ))}

            <div className="space-y-3 border-t pt-4 text-sm">
              <h4 className="font-medium">{t("match.advice")}</h4>
              {done.summary && <p>{done.summary}</p>}
              {!!done.strengths?.length && (
                <ul className="list-disc space-y-0.5 pl-5">
                  {done.strengths.map((s) => <li key={s}>{s}</li>)}
                </ul>
              )}
              {!!done.improvements?.length && (
                <ul className="space-y-2">
                  {done.improvements.map((i) => (
                    <li key={i.skill} className="rounded-md bg-secondary p-2.5">
                      <span className="font-medium">{i.skill}</span>
                      <p className="text-muted-foreground">{i.suggestion}</p>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </>
        )}

        <div className={cn("space-y-2", done && "border-t pt-4")}>
          <Button variant="outline" className="w-full"
            disabled={running || generate.isPending || !ai.ready || application.skills.length === 0}
            title={ai.reason ?? undefined} onClick={() => generate.mutate()}>
            {running || generate.isPending ? <Loader2 className="animate-spin" /> : <Sparkles />}
            {done ? t("report.regenerate") : t("report.generate")}
          </Button>
          {!ai.ready && !running && <p className="text-xs text-muted-foreground">{ai.reason}</p>}
          <ErrorText error={generate.error} />
        </div>
      </CardContent>
    </Card>
  )
}
