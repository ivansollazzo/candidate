import { json, request } from "@/shared/lib/http"

/** Schedule and cleanup of the automatic backups, see backup/backup.py */
export interface BackupSettings {
  frequency: "off" | "daily" | "weekly"
  /** Hour and weekday (Monday 0) in `timezone`, the time zone of the browser that saved them */
  hour: number
  weekday: number
  timezone: string
  /** Automatic backups kept, and the age after which they are removed (0 = no limit) */
  keep: number
  max_age_days: number
}

export interface Backup {
  name: string
  /** update: before an update; restore: the state replaced by a restore */
  kind: "auto" | "manual" | "update" | "restore" | string
  note: string
  created_at: string | null
  version: string
  build: string
  revision: string | null
  size: number
  broken: boolean
}

export interface Backups {
  settings: BackupSettings
  backups: Backup[]
  running: { operation: string; started_at: string } | null
  last_auto: { result: "ok" | "failed"; detail: string; at: string | null } | null
  last_restore: { name: string; result: "ok" | "failed"; detail: string; finished_at: string } | null
}

export const backupFileUrl = (name: string) => `/api/backups/${encodeURIComponent(name)}/file`

export const backupsApi = {
  getBackups: () => request<Backups>("/api/backups"),
  saveBackupSettings: (settings: BackupSettings) => request<BackupSettings>("/api/backups/settings", json("PUT", settings)),
  createBackup: (note: string) => request<Backup>("/api/backups", json("POST", { note })),
  deleteBackup: (name: string) => request<void>(`/api/backups/${encodeURIComponent(name)}`, { method: "DELETE" }),
  restoreBackup: (name: string) => request<void>(`/api/backups/${encodeURIComponent(name)}/restorations`, { method: "POST" }),
}
