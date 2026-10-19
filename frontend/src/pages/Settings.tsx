import { Navigate, useSearchParams } from "react-router"

import { AccountTab } from "@/components/settings/AccountTab"
import { AppearanceTab } from "@/components/settings/AppearanceTab"
import { InfoTab } from "@/components/settings/InfoTab"
import { SecurityTab } from "@/components/settings/SecurityTab"
import { SystemTab } from "@/components/settings/SystemTab"
import { UpdatesTab } from "@/components/settings/UpdatesTab"
import { UsersTab } from "@/components/settings/UsersTab"
import { useCurrentUser } from "@/lib/auth"
import { type MessageKey, useT } from "@/lib/i18n"
import { useSettings } from "@/lib/settings"
import { usePageTitle } from "@/lib/title"
import { useUpdates } from "@/lib/updates"
import { cn } from "@/lib/utils"

type Tab = "account" | "appearance" | "system" | "security" | "users" | "updates" | "info"

const TABS: { id: Tab; label: MessageKey; admin?: boolean }[] = [
  { id: "account", label: "settings.tabAccount" },
  { id: "appearance", label: "settings.tabAppearance" },
  { id: "system", label: "settings.tabSystem", admin: true },
  { id: "security", label: "settings.tabSecurity", admin: true },
  { id: "users", label: "settings.tabUsers", admin: true },
  { id: "updates", label: "settings.tabUpdates", admin: true },
  { id: "info", label: "settings.tabInfo" },
]

/** Tabbed settings; system, security, users and updates tabs are admin-only. */
export function SettingsPage() {
  const t = useT()
  usePageTitle(t("settings.title"))
  const me = useCurrentUser()
  const settings = useSettings()
  const updateAvailable = useUpdates().data?.update_available
  const [params, setParams] = useSearchParams()
  if (!me) return null

  const tabs = TABS.filter((tab) => !tab.admin || me.role === "admin")
  const tab = tabs.find((item) => item.id === params.get("tab"))?.id
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
        {tab === "system" && <SystemTab />}
        {tab === "security" && settings && <SecurityTab settings={settings} />}
        {tab === "users" && <UsersTab me={me} />}
        {tab === "updates" && <UpdatesTab />}
        {tab === "info" && <InfoTab />}
      </div>
    </div>
  )
}
