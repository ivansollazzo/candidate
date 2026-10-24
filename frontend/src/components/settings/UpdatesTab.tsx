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
  if (last.result === "failed") return <Failure message={t(`updates.error.${last.error || "build"}`)} detail={last.detail} />
  if (!last.restart_required && !last.stashed) return null
  return (
    <div className="space-y-1 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">
      {last.restart_required && (
        <p>{t("updates.restartRequired")} <code className="font-mono">docker compose up --build -d</code></p>
      )}
      {last.stashed && <p>{t("updates.stashed")}</p>}
    </div>
  )
}

/** Installed release, selected branch, check interval and branches of the repository (admin only). */
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
  const selected = data.branches.find((branch) => branch.name === data.selected_branch)
  const onInstall = () => {
    if (selected && confirm(t("updates.confirm", { version: release(selected), branch: selected.name }))) {
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
              <span>{t("updates.available", { version: release(selected), branch: selected.name })}</span>
              <Button size="sm" className="ml-auto" disabled={busy} onClick={onInstall}>
                <Download /> {t("updates.update")}
              </Button>
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
            <Label className="mb-1 block" htmlFor="update-branch">{t("updates.branch")}</Label>
            <Select id="update-branch" className="w-full sm:w-96" value={data.selected_branch ?? ""}
              disabled={save.isPending} onChange={(e) => save.mutate({ update_branch: e.target.value })}>
              {data.branches.map((branch) => (
                <option key={branch.name} value={branch.name}>
                  {branch.name} · {branch.version ? release(branch) : t("updates.noVersion")}
                </option>
              ))}
              {/* A selected branch that was deleted from the repository */}
              {settings.update_branch && !data.branches.some((branch) => branch.name === settings.update_branch) && (
                <option value={settings.update_branch}>{settings.update_branch}</option>
              )}
            </Select>
            <p className="mt-1 text-xs text-muted-foreground">
              {!selected ? t("updates.selectedMissing")
                : selected.newer ? t("updates.selectedNewer")
                  : t("updates.selectedWaiting", { branch: selected.name })}
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
        <CardHeader><CardTitle>{t("updates.branches")}</CardTitle></CardHeader>
        <CardContent className="space-y-3 text-sm">
          <p className="text-muted-foreground">{t("updates.branchesHint")}</p>
          {data.branches.length > 0 ? (
            <ul className="divide-y rounded-lg border">
              {data.branches.map((branch) => (
                <li key={branch.name} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2">
                  <span className="font-mono font-medium">{branch.name}</span>
                  {branch.name === data.selected_branch && (
                    <span className="rounded-full bg-secondary px-2 py-0.5 text-xs font-medium">{t("updates.selected")}</span>
                  )}
                  <span className="ml-auto text-muted-foreground">
                    {branch.version ? release(branch) : t("updates.noVersion")}
                    {branch.newer && <span className="ml-2 text-emerald-700 dark:text-emerald-400">{t("updates.newer")}</span>}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted-foreground">{t("updates.noBranches")}</p>
          )}
        </CardContent>
      </Card>
    </>
  )
}
