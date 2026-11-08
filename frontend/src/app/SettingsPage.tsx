import { Navigate, useSearchParams } from "react-router"

import { useCurrentUser } from "@/features/auth/hooks"
import { BackupsTab } from "@/features/backups/BackupsTab"
import { AiTab } from "@/features/settings/AiTab"
import { InfoTab } from "@/features/settings/InfoTab"
import { SecurityTab } from "@/features/settings/SecurityTab"
import { useSettings } from "@/features/settings/hooks"
import { UpdatesTab } from "@/features/updates/UpdatesTab"
import { useUpdates } from "@/features/updates/hooks"
import { AccountTab } from "@/features/users/AccountTab"
import { AppearanceTab } from "@/features/users/AppearanceTab"
import { UsersTab } from "@/features/users/UsersTab"
import { type MessageKey, useT } from "@/shared/lib/i18n"
import { usePageTitle } from "@/shared/lib/title"
import { cn } from "@/shared/lib/utils"

type Tab = "account" | "appearance" | "ai" | "security" | "users" | "updates" | "backups" | "info"

const TABS: { id: Tab; label: MessageKey; admin?: boolean }[] = [
  { id: "account", label: "settings.tabAccount" },
  { id: "appearance", label: "settings.tabAppearance" },
  { id: "ai", label: "settings.tabAi", admin: true },
  { id: "security", label: "settings.tabSecurity", admin: true },
  { id: "users", label: "settings.tabUsers", admin: true },
  { id: "updates", label: "settings.tabUpdates", admin: true },
  { id: "backups", label: "settings.tabBackups", admin: true },
  { id: "info", label: "settings.tabInfo" },
]

/** Tabbed settings; AI, security (with HTTPS), users, updates and backups tabs are admin-only. */
export function SettingsPage() {
  const t = useT()
  usePageTitle(t("settings.title"))
  const me = useCurrentUser()
  const settings = useSettings()
  const updateAvailable = useUpdates().data?.update_available
  const [params, setParams] = useSearchParams()
  if (!me) return null

  const tabs = TABS.filter((tab) => !tab.admin || me.role === "admin")
  const requested = params.get("tab") ?? ""
  const tab = tabs.find((item) => item.id === requested)?.id
  if (!tab) return <Navigate to="?tab=account" replace />

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <h1 className="text-xl font-semibold">{t("settings.title")}</h1>
      <nav role="tablist" className="-mx-4 flex gap-1 overflow-x-auto border-b px-4">
        {tabs.map((item) => (
          <button key={item.id} type="button" role="tab" aria-selected={tab === item.id}
            onClick={() => setParams({ tab: item.id })}
            className={cn("-mb-px whitespace-nowrap border-b-2 border-transparent px-3 py-2 text-sm text-muted-foreground hover:text-foreground",
              tab === item.id && "border-foreground font-medium text-foreground")}>
            {t(item.label)}
            {item.id === "updates" && updateAvailable && (
              <span className="ml-1.5 inline-block size-2 rounded-full bg-emerald-500" aria-label={t("updates.badge")} />
            )}
          </button>
        ))}
      </nav>
      <div className="space-y-5">
        {tab === "account" && <AccountTab me={me} />}
        {tab === "appearance" && <AppearanceTab />}
        {tab === "ai" && <AiTab />}
        {tab === "security" && settings && <SecurityTab settings={settings} />}
        {tab === "users" && <UsersTab me={me} />}
        {tab === "updates" && <UpdatesTab />}
        {tab === "backups" && <BackupsTab />}
        {tab === "info" && <InfoTab />}
      </div>
    </div>
  )
}
