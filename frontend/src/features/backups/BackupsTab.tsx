import { Download, History, Loader2, Save, Trash2 } from "lucide-react"
import { type FormEvent, useState } from "react"

import { type Backup, backupFileUrl, type Backups, type BackupSettings } from "@/features/backups/api"
import { useBackups, useCreateBackup, useDeleteBackup, useRestoreBackup, useSaveBackupSettings } from "@/features/backups/hooks"
import { Failure } from "@/features/updates/UpdatesTab"
import { useUpdates } from "@/features/updates/hooks"
import { ErrorText } from "@/shared/components/ErrorText"
import { dateLocale, formatDateTime, getLocale, type MessageKey, useT } from "@/shared/lib/i18n"
import { cn } from "@/shared/lib/utils"
import { Button, buttonVariants } from "@/shared/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card"
import { Input, Label, Select } from "@/shared/ui/input"

const KINDS: Record<string, MessageKey> = {
  auto: "backups.kind.auto",
  manual: "backups.kind.manual",
  update: "backups.kind.update",
  restore: "backups.kind.restore",
}

function formatSize(bytes: number): string {
  const format = (n: number) => n.toLocaleString(getLocale(), { maximumFractionDigits: 1 })
  if (bytes < 1024 * 1024) return `${format(bytes / 1024)} KB`
  if (bytes < 1024 ** 3) return `${format(bytes / 1024 / 1024)} MB`
  return `${format(bytes / 1024 ** 3)} GB`
}

// 1 January 2024 was a Monday, weekday 0 for the backup service
const weekdayName = (day: number) => new Date(2024, 0, 1 + day).toLocaleDateString(dateLocale(), { weekday: "long" })

/** Creation time of a backup from its file name, e.g. candidate-20261102-030000-auto.tar.gz (UTC) */
function nameTime(name: string): string | null {
  const m = /^candidate-(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})/.exec(name)
  return m ? `${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6]}Z` : null
}

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, Math.round(value) || min))

/** Frequency, time and cleanup rules of the automatic backups. */
function ScheduleCard({ data }: { data: Backups }) {
  const t = useT()
  const save = useSaveBackupSettings()
  const [form, setForm] = useState<BackupSettings>(data.settings)
  const set = (changes: Partial<BackupSettings>) => setForm((current) => ({ ...current, ...changes }))
  const browserZone = Intl.DateTimeFormat().resolvedOptions().timeZone
  const changed = JSON.stringify(form) !== JSON.stringify(data.settings)
  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    save.mutate(form)
  }

  return (
    <Card>
      <CardHeader><CardTitle>{t("backups.schedule")}</CardTitle></CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="space-y-4 text-sm">
          <div className="grid gap-3 sm:grid-cols-3">
            <div>
              <Label className="mb-1 block" htmlFor="backup-frequency">{t("backups.frequency")}</Label>
              <Select id="backup-frequency" className="w-full" value={form.frequency}
                onChange={(e) => set({ frequency: e.target.value as BackupSettings["frequency"] })}>
                <option value="daily">{t("backups.frequency.daily")}</option>
                <option value="weekly">{t("backups.frequency.weekly")}</option>
                <option value="off">{t("backups.frequency.off")}</option>
              </Select>
            </div>
            {form.frequency === "weekly" && (
              <div>
                <Label className="mb-1 block" htmlFor="backup-weekday">{t("backups.weekday")}</Label>
                <Select id="backup-weekday" className="w-full capitalize" value={form.weekday}
                  onChange={(e) => set({ weekday: Number(e.target.value) })}>
                  {[0, 1, 2, 3, 4, 5, 6].map((day) => <option key={day} value={day}>{weekdayName(day)}</option>)}
                </Select>
              </div>
            )}
            {form.frequency !== "off" && (
              <div>
                <Label className="mb-1 block" htmlFor="backup-hour">{t("backups.hour")}</Label>
                <Select id="backup-hour" className="w-full" value={form.hour}
                  onChange={(e) => set({ hour: Number(e.target.value) })}>
                  {Array.from({ length: 24 }, (_, hour) => (
                    <option key={hour} value={hour}>{`${String(hour).padStart(2, "0")}:00`}</option>
                  ))}
                </Select>
              </div>
            )}
          </div>
          {form.frequency !== "off" && data.settings.timezone !== browserZone && (
            <p className="text-xs text-muted-foreground">
              {t("backups.timezone", { saved: data.settings.timezone, current: browserZone })}
            </p>
          )}

          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <Label className="mb-1 block" htmlFor="backup-keep">{t("backups.keep")}</Label>
              <Input id="backup-keep" type="number" min={1} max={365} value={form.keep}
                onChange={(e) => set({ keep: clamp(Number(e.target.value), 1, 365) })} />
            </div>
            <div>
              <Label className="mb-1 block" htmlFor="backup-age">{t("backups.maxAge")}</Label>
              <Input id="backup-age" type="number" min={0} max={3650} value={form.max_age_days}
                onChange={(e) => set({ max_age_days: clamp(Number(e.target.value), 0, 3650) })} />
            </div>
          </div>
          <p className="text-xs text-muted-foreground">{t("backups.cleanupHint")}</p>

          <div className="flex flex-wrap items-center gap-3">
            <Button type="submit" size="sm" disabled={!changed || save.isPending}>
              {save.isPending ? <Loader2 className="animate-spin" /> : <Save />} {t("common.save")}
            </Button>
            <ErrorText error={save.error} />
          </div>

          {data.last_auto?.result === "failed" ? (
            <Failure message={t("backups.autoFailed", { time: formatDateTime(data.last_auto.at) })} detail={data.last_auto.detail} />
          ) : data.last_auto ? (
            <p className="text-xs text-muted-foreground">{t("backups.autoOk", { time: formatDateTime(data.last_auto.at) })}</p>
          ) : null}
        </form>
      </CardContent>
    </Card>
  )
}

function BackupRow({ backup, canRestore }: { backup: Backup; canRestore: boolean }) {
  const t = useT()
  const remove = useDeleteBackup()
  const restore = useRestoreBackup()
  const when = formatDateTime(backup.created_at)
  // The backup made before a restore notes the restored one
  const restored = backup.kind === "restore" ? nameTime(backup.note) : null
  const note = restored ? t("backups.restoredNote", { time: formatDateTime(restored) }) : backup.note
  const onRestore = () => {
    if (confirm(t("backups.confirmRestore", { time: when }))) restore.mutate(backup.name)
  }
  const onDelete = () => {
    if (confirm(t("backups.confirmDelete", { time: when }))) remove.mutate(backup.name)
  }

  return (
    <li className="space-y-1 px-3 py-2">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="font-medium">{when}</span>
        <span className="rounded-full bg-secondary px-2 py-0.5 text-xs font-medium">
          {KINDS[backup.kind] ? t(KINDS[backup.kind]) : backup.kind}
        </span>
        {backup.broken && <span className="text-xs text-red-700 dark:text-red-400">{t("backups.broken")}</span>}
        <div className="ml-auto flex items-center gap-1">
          <Button variant="outline" size="sm" disabled={!canRestore || backup.broken || restore.isPending} onClick={onRestore}>
            {restore.isPending ? <Loader2 className="animate-spin" /> : <History />} {t("backups.restore")}
          </Button>
          <a href={backupFileUrl(backup.name)} download title={t("backups.download")} aria-label={t("backups.download")}
            className={cn(buttonVariants({ variant: "ghost", size: "icon" }))}>
            <Download />
          </a>
          <Button variant="ghost" size="icon" title={t("common.delete")} aria-label={t("common.delete")}
            disabled={remove.isPending} onClick={onDelete}>
            <Trash2 />
          </Button>
        </div>
      </div>
      <p className="text-xs text-muted-foreground">
        {[backup.version && `${backup.version} · build ${backup.build}`, formatSize(backup.size), note]
          .filter(Boolean).join(" · ")}
      </p>
      <ErrorText error={restore.error ?? remove.error} className="text-xs" />
    </li>
  )
}

/** Automatic, manual and pre-update backups: restore, download, delete (admin only). */
export function BackupsTab() {
  const t = useT()
  const { data, error, isPending } = useBackups()
  const activeJobs = useUpdates().data?.active_jobs ?? 0
  const create = useCreateBackup()
  const [note, setNote] = useState("")

  if (isPending) return null
  if (!data) {
    return (
      <Card>
        <CardHeader><CardTitle>{t("backups.title")}</CardTitle></CardHeader>
        <CardContent className="space-y-2 text-sm">
          <ErrorText error={error} />
          <p className="text-muted-foreground">{t("backups.unavailableHint")}</p>
        </CardContent>
      </Card>
    )
  }

  const running = create.isPending || data.running != null
  const onCreate = (event: FormEvent) => {
    event.preventDefault()
    create.mutate(note.trim(), { onSuccess: () => setNote("") })
  }
  const last = data.last_restore

  return (
    <>
      {last && (last.result === "failed"
        ? <Failure message={t("backups.restoreFailed", { time: formatDateTime(last.finished_at) })} detail={last.detail} />
        : (
          <p className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-200">
            {t("backups.restoreOk", { time: formatDateTime(last.finished_at) })}
          </p>
        ))}

      <ScheduleCard key={JSON.stringify(data.settings)} data={data} />

      <Card>
        <CardHeader><CardTitle>{t("backups.title")}</CardTitle></CardHeader>
        <CardContent className="space-y-3 text-sm">
          <p className="text-muted-foreground">{t("backups.intro")}</p>
          <form onSubmit={onCreate} className="flex flex-wrap gap-2">
            <Input className="min-w-0 flex-1 basis-56" maxLength={200} placeholder={t("backups.notePlaceholder")}
              aria-label={t("backups.notePlaceholder")} value={note} onChange={(e) => setNote(e.target.value)} />
            <Button type="submit" disabled={running}>
              {running ? <Loader2 className="animate-spin" /> : <Save />} {running ? t("backups.running") : t("backups.create")}
            </Button>
          </form>
          <ErrorText error={create.error} />
          {activeJobs > 0 && <p className="text-xs text-muted-foreground">{t("backups.jobsActive", { count: activeJobs })}</p>}

          {data.backups.length > 0 ? (
            <ul className="divide-y rounded-lg border">
              {data.backups.map((backup) => (
                <BackupRow key={backup.name} backup={backup} canRestore={!running && activeJobs === 0} />
              ))}
            </ul>
          ) : (
            <p className="text-muted-foreground">{t("backups.empty")}</p>
          )}
        </CardContent>
      </Card>
    </>
  )
}
