import { Download, Loader2, RefreshCw } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import type { BranchRelease, Updates } from "@/lib/api"
import { dateLocale, useT } from "@/lib/i18n"
import { useCheckUpdates, useInstallUpdate, useUpdates } from "@/lib/updates"

const release = (item: { version: string; build: string }) => `${item.version} · build ${item.build}`

const formatTime = (value: string | null) =>
  value ? new Date(value).toLocaleString(dateLocale(), { dateStyle: "medium", timeStyle: "short" }) : "—"

function LastResult({ last }: { last: NonNullable<Updates["last"]> }) {
  const t = useT()
  if (last.result === "failed") {
    return (
      <div className="space-y-1 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
        <p>{t(`updates.error.${last.error || "build"}`)}</p>
        {last.detail && (
          <details>
            <summary className="cursor-pointer text-xs">{t("updates.details")}</summary>
            <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap text-xs">{last.detail}</pre>
          </details>
        )}
      </div>
    )
  }
  if (!last.restart_required) return null
  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">
      {t("updates.restartRequired")} <code className="font-mono">docker compose up --build -d</code>
    </div>
  )
}

/** Installed release, branches of the repository and their versions (admin only). */
export function UpdatesTab() {
  const t = useT()
  const { data } = useUpdates()
  const check = useCheckUpdates()
  const install = useInstallUpdate()
  if (!data) return null

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
  const current = data.branches.find((branch) => branch.name === data.branch)
  const onInstall = (branch: BranchRelease) => {
    if (confirm(t("updates.confirm", { version: release(branch), branch: branch.name }))) {
      install.mutate({ branch: branch.name, build: data.build })
    }
  }
  const error = check.error ?? install.error

  return (
    <>
      {error && <p className="text-sm text-red-600 dark:text-red-400">{error.message}</p>}
      <Card>
        <CardHeader><CardTitle>{t("updates.installed")}</CardTitle></CardHeader>
        <CardContent className="space-y-3 text-sm">
          <dl className="grid gap-x-4 gap-y-1 sm:grid-cols-[10rem_1fr]">
            <dt className="text-muted-foreground">{t("info.version")}</dt>
            <dd className="font-mono">{release(data)}</dd>
            <dt className="text-muted-foreground">{t("updates.branch")}</dt>
            <dd className="font-mono">{data.branch ?? "—"} {data.commit && <span className="text-muted-foreground">({data.commit})</span>}</dd>
          </dl>
          {data.update_available && current && (
            <div className="flex flex-wrap items-center gap-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-emerald-900 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-200">
              <span>{t("updates.available", { version: release(current) })}</span>
              <Button size="sm" className="ml-auto" disabled={busy} onClick={() => onInstall(current)}>
                <Download /> {t("updates.update")}
              </Button>
            </div>
          )}
          {data.last && <LastResult last={data.last} />}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex-wrap">
          <CardTitle>{t("updates.branches")}</CardTitle>
          <Button variant="outline" size="sm" disabled={busy} onClick={() => check.mutate()}>
            {data.status === "checking" ? <Loader2 className="animate-spin" /> : <RefreshCw />} {t("updates.check")}
          </Button>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <p className="text-muted-foreground">{t("updates.branchesHint")}</p>
          {data.branches.length > 0 ? (
            <ul className="divide-y rounded-lg border">
              {data.branches.map((branch) => (
                <li key={branch.name} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2">
                  <span className="font-mono font-medium">{branch.name}</span>
                  {branch.name === data.branch && (
                    <span className="rounded-full bg-secondary px-2 py-0.5 text-xs font-medium">{t("updates.inUse")}</span>
                  )}
                  <span className="text-muted-foreground">
                    {branch.version ? release(branch) : t("updates.noVersion")}
                  </span>
                  <span className="ml-auto">
                    {branch.newer ? (
                      <Button variant="outline" size="sm" disabled={busy} onClick={() => onInstall(branch)}>
                        <Download /> {t("updates.install")}
                      </Button>
                    ) : (
                      <span className="text-xs text-muted-foreground">{t("updates.notNewer")}</span>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted-foreground">{t("updates.noBranches")}</p>
          )}
          <p className="text-xs text-muted-foreground">{t("updates.checkedAt", { time: formatTime(data.checked_at) })}</p>
        </CardContent>
      </Card>
    </>
  )
}
