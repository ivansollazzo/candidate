import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Banknote, MapPin, Plus, Search, Trash2 } from "lucide-react"
import { useEffect, useState, type InputHTMLAttributes } from "react"
import { Link, useSearchParams } from "react-router"

import { Button, buttonVariants } from "@/components/ui/button"
import { Input, Select } from "@/components/ui/input"
import { api, type ApplicationBulk, type ApplicationListItem, type ApplicationSort, type MeChanges, type User } from "@/lib/api"
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

function Checkbox({ indeterminate = false, ...props }: InputHTMLAttributes<HTMLInputElement> & { indeterminate?: boolean }) {
  return (
    <input type="checkbox" ref={(el) => { if (el) el.indeterminate = indeterminate }}
      className="size-4 shrink-0 cursor-pointer accent-primary" {...props} />
  )
}

function ApplicationRow({ app, showEvent, selected, onSelect, onStatus }: {
  app: ApplicationListItem
  showEvent: boolean
  selected: boolean
  onSelect: (selected: boolean) => void
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
    <li className={cn("relative flex gap-3 px-4 py-3 transition-colors hover:bg-secondary/50", selected && "bg-secondary/60")}>
      {/* Above the link that covers the row */}
      <div className="relative z-10 flex items-start pt-1 sm:items-center sm:pt-0">
        <Checkbox checked={selected} aria-label={t("list.select")} onChange={(e) => onSelect(e.target.checked)} />
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-3 sm:flex-row sm:items-center">
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
      </div>
    </li>
  )
}

export function ApplicationList() {
  const t = useT()
  usePageTitle(t("nav.applications"))
  const queryClient = useQueryClient()
  const [search, setSearch] = useState("")
  // Sort order and status filter are saved on the user, shown at once and stored in the background
  const me = useCurrentUser()
  const updateMe = useUpdateMe()
  const savePreference = (changes: MeChanges) => {
    queryClient.setQueryData<User>(["me"], (old) => old && { ...old, ...changes })
    updateMe.mutate(changes)
  }
  const sort = me?.application_sort ?? "applied"
  const saved = STATUSES.find((s) => s.value === me?.application_filter)?.value ?? null
  const setFilter = (status: ApplicationStatus | null) => savePreference({ application_filter: status ?? "all" })
  // The overview links to a pre-filtered list (?status=): that becomes the saved filter
  const [params, setParams] = useSearchParams()
  const linked = STATUSES.find((s) => s.value === params.get("status"))?.value
  const filter = linked ?? saved
  useEffect(() => {
    if (!params.has("status")) return
    if (linked) setFilter(linked)
    setParams({}, { replace: true })
  }, [params])
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

  // Selection for bulk actions; it is cleared when the filter or the search changes, so it never
  // covers applications that are not on screen
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const select = (ids: number[], on: boolean) => setSelected((old) => {
    const next = new Set(old)
    for (const id of ids) {
      if (on) next.add(id)
      else next.delete(id)
    }
    return next
  })
  const bulk = useMutation({
    mutationFn: api.bulkApplications,
    onSuccess: () => setSelected(new Set()),
    onSettled: () => {
      for (const key of ["applications", "application", "events"]) queryClient.invalidateQueries({ queryKey: [key] })
    },
  })

  const term = search.toLowerCase()
  useEffect(() => setSelected(new Set()), [filter, term])
  const matching = data.filter((a) =>
    !term || [a.title, a.company, a.location].some((v) => v?.toLowerCase().includes(term)))
  const visible = (filter ? matching.filter((a) => a.status === filter) : [...matching]).sort(COMPARE[sort])
  const chosen = visible.filter((a) => selected.has(a.id)).map((a) => a.id)
  const runBulk = (action: ApplicationBulk) => bulk.mutate(action)
  const onBulkDelete = () => {
    if (confirm(t("list.confirmBulkDelete", { count: chosen.length }))) runBulk({ ids: chosen, action: "delete" })
  }
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
            onChange={(e) => savePreference({ application_sort: e.target.value as ApplicationSort })}>
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

      {(error ?? bulk.error) && (
        <p className="text-sm text-red-600 dark:text-red-400">{((error ?? bulk.error) as Error).message}</p>
      )}
      {isLoading && <p className="text-sm text-muted-foreground">{t("common.loading")}</p>}

      {!isLoading && visible.length === 0 ? (
        <div className="rounded-xl border border-dashed p-10 text-center text-sm text-muted-foreground">
          {data.length === 0 ? t("list.empty") : t("list.noMatch")}
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border bg-card">
          <div className="flex min-h-12 flex-wrap items-center gap-3 border-b bg-secondary/30 px-4 py-2 text-sm">
            <label className="flex cursor-pointer items-center gap-3">
              <Checkbox checked={chosen.length > 0 && chosen.length === visible.length}
                indeterminate={chosen.length > 0 && chosen.length < visible.length}
                onChange={(e) => select(visible.map((a) => a.id), e.target.checked)} />
              <span className={chosen.length ? "font-medium" : "text-muted-foreground"}>
                {chosen.length ? t("list.selected", { count: chosen.length }) : t("list.selectAll")}
              </span>
            </label>
            {chosen.length > 0 && (
              <div className="ml-auto flex flex-wrap items-center gap-2">
                <Select className="h-8 w-48" value="" aria-label={t("list.bulkStatus")} disabled={bulk.isPending}
                  onChange={(e) => runBulk({ ids: chosen, action: "status", status: e.target.value as ApplicationStatus })}>
                  <option value="" disabled>{t("list.bulkStatus")}</option>
                  {STATUSES.map((s) => <option key={s.value} value={s.value}>{statusLabel(s.value)}</option>)}
                </Select>
                <Button variant="outline" size="sm" disabled={bulk.isPending} onClick={onBulkDelete}
                  className="text-red-600 hover:text-red-700 dark:text-red-400">
                  <Trash2 /> {t("common.delete")}
                </Button>
                <Button variant="ghost" size="sm" disabled={bulk.isPending} onClick={() => setSelected(new Set())}>
                  {t("list.clearSelection")}
                </Button>
              </div>
            )}
          </div>
          <ul className="divide-y">
            {visible.map((app) => (
              <ApplicationRow key={app.id} app={app} showEvent={sort === "event"} selected={selected.has(app.id)}
                onSelect={(on) => select([app.id], on)}
                onStatus={(status) => changeStatus.mutate({ id: app.id, status })} />
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
