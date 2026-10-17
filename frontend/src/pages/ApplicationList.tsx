import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Banknote, MapPin, Plus, Search } from "lucide-react"
import { useState } from "react"
import { Link, useSearchParams } from "react-router"

import { buttonVariants } from "@/components/ui/button"
import { Input, Select } from "@/components/ui/input"
import { api, type ApplicationListItem, type ApplicationSort } from "@/lib/api"
import { useCurrentUser, useUpdateMe } from "@/lib/auth"
import { useT } from "@/lib/i18n"
import { STATUSES, statusInfo, statusLabel, type ApplicationStatus } from "@/lib/status"
import { usePageTitle } from "@/lib/title"
import { cn, formatDate, formatSalary } from "@/lib/utils"

const SORTS: ApplicationSort[] = ["applied", "status", "name", "event"]
// Most advanced first: completed > offer > interview > applied > inactive > rejected
const STATUS_RANK: Record<ApplicationStatus, number> = {
  completed: 0, offer: 1, interview: 2, applied: 3, inactive: 4, rejected: 5,
}

// Newest first; missing dates go last
const byDateDesc = (a: string | null, b: string | null) => (b ?? "").localeCompare(a ?? "")
const byName = (a: ApplicationListItem, b: ApplicationListItem) =>
  (a.title ?? "").localeCompare(b.title ?? "", undefined, { sensitivity: "base" }) ||
  (a.company ?? "").localeCompare(b.company ?? "", undefined, { sensitivity: "base" })

const COMPARE: Record<ApplicationSort, (a: ApplicationListItem, b: ApplicationListItem) => number> = {
  applied: (a, b) => byDateDesc(a.applied_on, b.applied_on) || byName(a, b),
  status: (a, b) => STATUS_RANK[a.status] - STATUS_RANK[b.status] || byDateDesc(a.applied_on, b.applied_on),
  name: (a, b) => byName(a, b) || byDateDesc(a.applied_on, b.applied_on),
  event: (a, b) => byDateDesc(a.last_event_on, b.last_event_on) || byDateDesc(a.applied_on, b.applied_on),
}

function ApplicationRow({ app, showEvent, onStatus }: {
  app: ApplicationListItem
  showEvent: boolean
  onStatus: (status: ApplicationStatus) => void
}) {
  const t = useT()
  const salary = formatSalary(app.salary, app.salary_period, app.salary_basis)
  const status = statusInfo(app.status)
  const details = [
    app.location && <span key="loc" className="flex items-center gap-1"><MapPin className="size-3" />{app.location}</span>,
    salary && <span key="sal" className="flex items-center gap-1"><Banknote className="size-3" />{salary}</span>,
  ].filter(Boolean)

  return (
    <li className="relative flex flex-col gap-3 px-4 py-3 transition-colors hover:bg-secondary/50 sm:flex-row sm:items-center">
      <div className="min-w-0 flex-1">
        <p className="truncate">
          {/* The link covers the whole row; the status menu stays clickable on top */}
          <Link to={`/applications/${app.id}`} className="font-medium after:absolute after:inset-0">
            {app.title ?? t("application.untitled")}
          </Link>
          <span className="text-muted-foreground"> · {app.company ?? t("application.noCompany")}</span>
        </p>
        {details.length > 0 && (
          <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">{details}</div>
        )}
      </div>
      <div className="relative z-10 flex items-center gap-3">
        <span className="hidden w-36 whitespace-nowrap text-right text-xs text-muted-foreground md:block">
          {showEvent
            ? app.last_event_on && t("list.lastEvent", { date: formatDate(app.last_event_on) ?? "" })
            : app.applied_on && t("list.appliedOn", { date: formatDate(app.applied_on) ?? "" })}
        </span>
        <span className={cn("size-2 shrink-0 rounded-full", status.color)} />
        <Select className="w-48" value={app.status} aria-label={t("list.statusLabel")}
          onChange={(e) => onStatus(e.target.value as ApplicationStatus)}>
          {STATUSES.map((s) => <option key={s.value} value={s.value}>{statusLabel(s.value)}</option>)}
        </Select>
      </div>
    </li>
  )
}

export function ApplicationList() {
  const t = useT()
  usePageTitle(t("nav.applications"))
  const queryClient = useQueryClient()
  const [search, setSearch] = useState("")
  // Filter lives in the URL so the overview can link to a pre-filtered list
  const [params, setParams] = useSearchParams()
  const filter = STATUSES.find((s) => s.value === params.get("status"))?.value ?? null
  const setFilter = (status: ApplicationStatus | null) => setParams(status ? { status } : {}, { replace: true })
  // Sort order is saved on the user
  const me = useCurrentUser()
  const updateMe = useUpdateMe()
  const sort = (updateMe.isPending && updateMe.variables.application_sort) || me?.application_sort || "applied"
  const { data = [], isLoading, error } = useQuery({ queryKey: ["applications"], queryFn: api.listApplications })
  const changeStatus = useMutation({
    mutationFn: ({ id, status }: { id: number; status: ApplicationStatus }) => api.updateApplication(id, { status }),
    onMutate: ({ id, status }) => {
      queryClient.setQueryData<ApplicationListItem[]>(["applications"], (old) =>
        old?.map((a) => (a.id === id ? { ...a, status } : a)))
    },
    onSettled: (_data, _error, { id }) => {
      queryClient.invalidateQueries({ queryKey: ["applications"] })
      queryClient.invalidateQueries({ queryKey: ["application", id] })
    },
  })

  const term = search.toLowerCase()
  const matching = data.filter((a) =>
    !term || [a.title, a.company, a.location].some((v) => v?.toLowerCase().includes(term)))
  const visible = (filter ? matching.filter((a) => a.status === filter) : [...matching]).sort(COMPARE[sort])
  const chip = (active: boolean) => cn(
    "flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm text-muted-foreground hover:text-foreground",
    active && "border-foreground/30 bg-secondary text-foreground",
  )

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold">{t("nav.applications")}</h1>
        <span className="text-sm text-muted-foreground">{t("list.total", { count: data.length })}</span>
        <label className="ml-auto flex items-center gap-2 text-sm text-muted-foreground">
          {t("list.sortLabel")}
          <Select className="w-44 text-foreground" value={sort}
            onChange={(e) => updateMe.mutate({ application_sort: e.target.value as ApplicationSort })}>
            {SORTS.map((s) => <option key={s} value={s}>{t(`list.sort.${s}`)}</option>)}
          </Select>
        </label>
        <div className="relative w-full max-w-xs">
          <Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
          <Input className="pl-8" placeholder={t("list.search")} value={search}
            onChange={(e) => setSearch(e.target.value)} />
        </div>
        <Link to="/applications/new" className={buttonVariants()}><Plus />{t("new.title")}</Link>
      </div>

      <div className="flex flex-wrap gap-2">
        <button type="button" className={chip(filter == null)} onClick={() => setFilter(null)}>
          {t("list.all")} <span className="text-muted-foreground">{matching.length}</span>
        </button>
        {STATUSES.map((s) => (
          <button key={s.value} type="button" className={chip(filter === s.value)}
            onClick={() => setFilter(filter === s.value ? null : s.value)}>
            <span className={cn("size-2 rounded-full", s.color)} />
            {statusLabel(s.value)}
            <span className="text-muted-foreground">{matching.filter((a) => a.status === s.value).length}</span>
          </button>
        ))}
      </div>

      {error && <p className="text-sm text-red-600 dark:text-red-400">{(error as Error).message}</p>}
      {isLoading && <p className="text-sm text-muted-foreground">{t("common.loading")}</p>}

      {!isLoading && visible.length === 0 ? (
        <div className="rounded-xl border border-dashed p-10 text-center text-sm text-muted-foreground">
          {data.length === 0 ? t("list.empty") : t("list.noMatch")}
        </div>
      ) : (
        <ul className="divide-y overflow-hidden rounded-xl border bg-card">
          {visible.map((app) => (
            <ApplicationRow key={app.id} app={app} showEvent={sort === "event"} onStatus={(status) => changeStatus.mutate({ id: app.id, status })} />
          ))}
        </ul>
      )}
    </div>
  )
}
