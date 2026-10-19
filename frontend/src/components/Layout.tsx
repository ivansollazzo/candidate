import { useQuery } from "@tanstack/react-query"
import { Briefcase, CalendarDays, LayoutDashboard, LogOut, Settings } from "lucide-react"
import { Link, Navigate, Outlet, useLocation } from "react-router"

import { Avatar } from "@/components/Avatar"
import { UpdateScreen } from "@/components/UpdateScreen"
import { api } from "@/lib/api"
import { useCurrentUser, useLogout } from "@/lib/auth"
import { type MessageKey, useT } from "@/lib/i18n"
import { useUpdates } from "@/lib/updates"
import { cn } from "@/lib/utils"

// Keep "Applications" highlighted on the detail and new-application pages too
const links: { to: string; label: MessageKey; icon: typeof Briefcase; isActive: (path: string) => boolean }[] = [
  { to: "/", label: "nav.overview", icon: LayoutDashboard, isActive: (path) => path === "/" },
  { to: "/applications", label: "nav.applications", icon: Briefcase, isActive: (path) => /^\/applications/.test(path) },
  { to: "/agenda", label: "nav.agenda", icon: CalendarDays, isActive: (path) => path.startsWith("/agenda") },
]

const linkClass = (active: boolean) => cn(
  "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground",
  active && "bg-secondary text-foreground",
)

export function Layout() {
  const t = useT()
  const { pathname } = useLocation()
  const me = useCurrentUser()
  const logout = useLogout()
  const { data: profile } = useQuery({ queryKey: ["profile"], queryFn: api.getProfile })
  const updateAvailable = useUpdates().data?.update_available
  if (!me) return null
  // First login starts with the initial setup
  if (!me.onboarded) return <Navigate to="/welcome" replace />

  const onProfile = pathname.startsWith("/profile")
  const onSettings = pathname.startsWith("/settings")

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-10 border-b bg-background/90 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-7xl items-center gap-6 px-4">
          <nav className="flex gap-1">
            {links.map(({ to, label, icon: Icon, isActive }) => (
              <Link key={to} to={to} aria-current={isActive(pathname) ? "page" : undefined}
                className={linkClass(isActive(pathname))}>
                <Icon className="size-4" />
                <span className="hidden sm:inline">{t(label)}</span>
              </Link>
            ))}
          </nav>
          <nav className="ml-auto flex gap-1">
            {/* Show photo and full name when set */}
            <Link to="/profile" aria-current={onProfile ? "page" : undefined} className={linkClass(onProfile)}
              title={t("nav.profile")}>
              <Avatar user={me} className="-my-1 size-6" />
              <span className="hidden max-w-48 truncate sm:inline">{profile?.full_name || me.username}</span>
            </Link>
            <Link to={updateAvailable ? "/settings?tab=updates" : "/settings"} aria-current={onSettings ? "page" : undefined}
              className={cn(linkClass(onSettings), "relative")} aria-label={t("nav.settings")}
              title={updateAvailable ? t("updates.badge") : t("nav.settings")}>
              <Settings className="size-4" />
              {updateAvailable && <span className="absolute right-1.5 top-1 size-2 rounded-full bg-emerald-500" />}
            </Link>
            <button type="button" className={linkClass(false)} aria-label={t("nav.logout")} title={t("nav.logout")}
              disabled={logout.isPending} onClick={() => logout.mutate()}>
              <LogOut className="size-4" />
            </button>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6">
        <Outlet />
      </main>
      <UpdateScreen />
    </div>
  )
}
