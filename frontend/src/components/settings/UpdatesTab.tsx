import { Download, Loader2, RefreshCw } from "lucide-react"

import { ErrorText } from "@/components/ErrorText"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Label, Select } from "@/components/ui/input"
import type { Updates } from "@/lib/api"
import { dateLocale, useT } from "@/lib/i18n"
import { useSettings, useUpdateSettings } from "@/lib/settings"
import { useCheckUpdates, useInstallUpdate, useUpdates } from "@/lib/updates"

// Hours between checks; 0 = only with "Check now"
const CHECK_INTERVALS = [1, 6, 12, 24, 168, 0] as const

const release = (item: { version: string; build: string }) => `${item.version} · build ${item.build}`

type Source = Updates["sources"][number]

const formatTime = (value: string | null) =>
  value ? new Date(value).toLocaleString(dateLocale(), { dateStyle: "medium", timeStyle: "short" }) : "—"

function Failure({ message, detail }: { message: string; detail: string }) {
  const t = useT()
  return (
    <div className="space-y-1 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
      <p>{message}</p>
      {detail && (
        <details>
          <summary className="cursor-pointer text-xs">{t("updates.details")}</summary>
          <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap text-xs">{detail}</pre>
        </details>
      )}
    </div>
  )
}

function LastResult({ last }: { last: NonNullable<Updates["last"]> }) {
  const t = useT()
  if (last.result !== "failed") return null
  return <Failure message={t(`updates.error.${last.error || "start"}`)} detail={last.detail} />
}

/** Installed release, followed channel or branch, check interval and available releases (admin only). */
export function UpdatesTab() {
  const t = useT()
  const { data } = useUpdates()
  const settings = useSettings()
  const save = useUpdateSettings()
  const check = useCheckUpdates()
  const install = useInstallUpdate()
  if (!data || !settings) return null

  if (data.status === "unavailable") {
    return (
      <Card>
        <CardHeader><CardTitle>{t("updates.title")}</CardTitle></CardHeader>
        <CardContent className="space-y-2 text-sm text-muted-foreground">
          <p>{t("updates.unavailable")}</p>
          <p>{t("updates.unavailableHint")}</p>
        </CardContent>
      </Card>
    )
  }

  const busy = data.status !== "idle" || check.isPending || install.isPending
  const name = (source: Source) => (source.kind === "channel"
    ? t(`updates.channel.${source.name === "@beta" ? "beta" : "stable"}`) : source.name)
  const selected = data.sources.find((source) => source.name === data.selected_source)
  const channels = data.sources.filter((source) => source.kind === "channel")
  const branches = data.sources.filter((source) => source.kind === "branch")
  const option = (source: Source) => (
    <option key={source.name} value={source.name}>
      {name(source)} · {source.version ? release(source) : t("updates.noVersion")}
    </option>
  )
  const onInstall = () => {
    if (selected && confirm(t("updates.confirm", { version: release(selected), source: name(selected) }))) {
      install.mutate({ build: data.build })
    }
  }
  const error = save.error ?? check.error ?? install.error

  return (
    <>
      <ErrorText error={error} />
      <Card>
        <CardHeader><CardTitle>{t("updates.installed")}</CardTitle></CardHeader>
        <CardContent className="space-y-3 text-sm">
          <dl className="grid gap-x-4 gap-y-1 sm:grid-cols-[10rem_1fr]">
            <dt className="text-muted-foreground">{t("info.version")}</dt>
            <dd className="font-mono">{data.version}</dd>
            <dt className="text-muted-foreground">{t("info.build")}</dt>
            <dd className="font-mono">{data.build}</dd>
          </dl>
          {data.update_available && selected && (
            <div className="flex flex-wrap items-center gap-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-emerald-900 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-200">
              <span>{t("updates.available", { version: release(selected), source: name(selected) })}</span>
              <Button size="sm" className="ml-auto" disabled={busy || data.active_jobs > 0} onClick={onInstall}>
                <Download /> {t("updates.update")}
              </Button>
              {data.active_jobs > 0 && (
                <p className="w-full text-xs">{t("updates.jobsActive", { count: data.active_jobs })}</p>
              )}
            </div>
          )}
          {data.last && <LastResult last={data.last} />}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex-wrap">
          <CardTitle>{t("updates.settings")}</CardTitle>
          <Button variant="outline" size="sm" disabled={busy} onClick={() => check.mutate()}>
            {data.status === "checking" ? <Loader2 className="animate-spin" /> : <RefreshCw />} {t("updates.check")}
          </Button>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
          <div>
            <Label className="mb-1 block" htmlFor="update-source">{t("updates.source")}</Label>
            <Select id="update-source" className="w-full sm:w-96" value={data.selected_source}
              disabled={save.isPending} onChange={(e) => save.mutate({ update_source: e.target.value })}>
              {/* A channel without releases yet, or a branch deleted from the repository */}
              {!selected && (
                <option value={data.selected_source}>
                  {data.selected_source.startsWith("@")
                    ? t(`updates.channel.${data.selected_source === "@beta" ? "beta" : "stable"}`) : data.selected_source}
                </option>
              )}
              {channels.length > 0 && <optgroup label={t("updates.channels")}>{channels.map(option)}</optgroup>}
              {branches.length > 0 && <optgroup label={t("updates.branches")}>{branches.map(option)}</optgroup>}
            </Select>
            <p className="mt-1 text-xs text-muted-foreground">
              {!selected ? t(data.selected_source.startsWith("@") ? "updates.channelEmpty" : "updates.selectedMissing")
                : !selected.newer ? t("updates.selectedWaiting")
                  : selected.published ? t("updates.selectedNewer") : t("updates.selectedBuilding")}
            </p>
          </div>
          <div>
            <Label className="mb-1 block" htmlFor="update-interval">{t("updates.interval")}</Label>
            <Select id="update-interval" className="w-full sm:w-96" value={settings.update_check_hours}
              disabled={save.isPending} onChange={(e) => save.mutate({ update_check_hours: Number(e.target.value) })}>
              {CHECK_INTERVALS.map((hours) => (
                <option key={hours} value={hours}>{t(`updates.every.${hours}`)}</option>
              ))}
            </Select>
            <p className="mt-1 text-xs text-muted-foreground">
              {t("updates.checkedAt", { time: formatTime(data.checked_at) })}
            </p>
          </div>
          {data.check_error && (
            <Failure message={t("updates.error.check", { time: formatTime(data.check_error.failed_at) })}
              detail={data.check_error.detail} />
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>{t("updates.releases")}</CardTitle></CardHeader>
        <CardContent className="space-y-3 text-sm">
          <p className="text-muted-foreground">{t("updates.releasesHint")}</p>
          {data.sources.length > 0 ? (
            <ul className="divide-y rounded-lg border">
              {data.sources.map((source) => (
                <li key={source.name} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2">
                  <span className={source.kind === "branch" ? "font-mono font-medium" : "font-medium"}>{name(source)}</span>
                  {source.tag && <span className="font-mono text-xs text-muted-foreground">{source.tag}</span>}
                  {source.name === data.selected_source && (
                    <span className="rounded-full bg-secondary px-2 py-0.5 text-xs font-medium">{t("updates.selected")}</span>
                  )}
                  <span className="ml-auto text-muted-foreground">
                    {source.version ? release(source) : t("updates.noVersion")}
                    {source.newer && (source.published
                      ? <span className="ml-2 text-emerald-700 dark:text-emerald-400">{t("updates.newer")}</span>
                      : <span className="ml-2 text-amber-700 dark:text-amber-400">{t("updates.building")}</span>)}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted-foreground">{t("updates.noReleases")}</p>
          )}
        </CardContent>
      </Card>
    </>
  )
}
