import {
  closestCenter, DndContext, type DragEndEvent, KeyboardSensor, PointerSensor, TouchSensor, useSensor, useSensors,
} from "@dnd-kit/core"
import { arrayMove, rectSortingStrategy, SortableContext, sortableKeyboardCoordinates, useSortable } from "@dnd-kit/sortable"
import { CSS } from "@dnd-kit/utilities"
import { useQuery } from "@tanstack/react-query"
import { Check, GripVertical, Maximize2, Minimize2, Paintbrush, Plus, RotateCcw, X } from "lucide-react"
import { useEffect, useRef, useState } from "react"

import { DEFAULT_LAYOUT, type OverviewData, WIDGETS } from "@/app/OverviewWidgets"
import { applicationsApi } from "@/features/applications/api"
import type { OverviewWidget, WidgetId } from "@/features/auth/api"
import { useCurrentUser, useSavePreference } from "@/features/auth/hooks"
import { profileApi } from "@/features/profile/api"
import { useAiStatus } from "@/features/settings/ai"
import { ErrorText } from "@/shared/components/ErrorText"
import { t, useT } from "@/shared/lib/i18n"
import { usePageTitle } from "@/shared/lib/title"
import { cn, today } from "@/shared/lib/utils"
import { Button } from "@/shared/ui/button"

const toolButton = "flex size-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"

/** A widget in the grid; while editing it can be dragged by its handle, resized and removed. */
function WidgetSlot({ widget, data, editing, onResize, onRemove }: {
  widget: OverviewWidget
  data: OverviewData
  editing: boolean
  onResize: () => void
  onRemove: () => void
}) {
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } =
    useSortable({ id: widget.id, disabled: !editing })
  const info = WIDGETS[widget.id]
  return (
    <div ref={setNodeRef} style={{ transform: CSS.Translate.toString(transform), transition }}
      className={cn("relative min-w-0", widget.size === "full" && "lg:col-span-2",
        editing && "rounded-xl outline-2 outline-offset-4 outline-dashed outline-border",
        isDragging && "z-20 opacity-80 shadow-2xl")}>
      {editing && (
        <div className="absolute bottom-full right-0 z-10 mb-2 flex items-center gap-0.5 rounded-lg border bg-background p-0.5 shadow-md">
          <span className="max-w-40 truncate px-1.5 text-xs font-medium">{info.title()}</span>
          <button ref={setActivatorNodeRef} type="button" className={cn(toolButton, "cursor-grab touch-none active:cursor-grabbing")}
            aria-label={t("overview.edit.move")} title={t("overview.edit.move")} {...attributes} {...listeners}>
            <GripVertical className="size-4" />
          </button>
          <button type="button" className={cn(toolButton, "max-lg:hidden")} onClick={onResize}
            title={widget.size === "full" ? t("overview.edit.half") : t("overview.edit.full")}
            aria-label={widget.size === "full" ? t("overview.edit.half") : t("overview.edit.full")}>
            {widget.size === "full" ? <Minimize2 className="size-3.5" /> : <Maximize2 className="size-3.5" />}
          </button>
          <button type="button" className={cn(toolButton, "hover:text-red-600 dark:hover:text-red-400")} onClick={onRemove}
            title={t("overview.edit.remove")} aria-label={t("overview.edit.remove")}>
            <X className="size-4" />
          </button>
        </div>
      )}
      {/* Links and buttons inside the widgets don't react while editing */}
      <div className={cn("h-full", editing && "pointer-events-none select-none")} inert={editing}>
        {info.render({ data, size: widget.size })}
      </div>
    </div>
  )
}

/** Tile that lists the widgets not on the overview yet. */
function AddWidget({ missing, onAdd }: { missing: WidgetId[]; onAdd: (id: WidgetId) => void }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const close = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false) }
    const escape = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false) }
    document.addEventListener("mousedown", close)
    document.addEventListener("keydown", escape)
    return () => {
      document.removeEventListener("mousedown", close)
      document.removeEventListener("keydown", escape)
    }
  }, [open])
  if (missing.length === 0) return null
  return (
    <div ref={ref} className="relative">
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open}
        className="flex min-h-28 w-full items-center justify-center gap-2 rounded-xl border-2 border-dashed text-sm font-medium text-muted-foreground transition-colors hover:border-foreground/30 hover:bg-secondary/40 hover:text-foreground">
        <Plus className="size-4" />{t("overview.edit.add")}
      </button>
      {open && (
        <ul className="absolute inset-x-0 top-full z-30 mt-2 max-h-96 overflow-y-auto rounded-xl border bg-background p-1.5 shadow-xl">
          {missing.map((id) => (
            <li key={id}>
              <button type="button" className="w-full rounded-lg px-3 py-2 text-left hover:bg-accent"
                onClick={() => { onAdd(id); setOpen(false) }}>
                <span className="block text-sm font-medium">{WIDGETS[id].title()}</span>
                <span className="block text-xs text-muted-foreground">{WIDGETS[id].description()}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export function Overview() {
  useT()
  usePageTitle(t("overview.title"))
  const { data: applications = [], isLoading, error } = useQuery({ queryKey: ["applications"], queryFn: applicationsApi.listApplications })
  const { data: profile } = useQuery({ queryKey: ["profile"], queryFn: profileApi.getProfile })
  const { data: events = [] } = useQuery({ queryKey: ["events"], queryFn: applicationsApi.listEvents })
  const ai = useAiStatus()
  const [day, setDay] = useState(today)
  const [editing, setEditing] = useState(false)

  // The layout is a preference of the user; widgets unknown to this version are left out
  const me = useCurrentUser()
  const savePreference = useSavePreference()
  const layout = (me?.overview_layout ?? DEFAULT_LAYOUT).filter((w) => w.id in WIDGETS)
  const save = (next: OverviewWidget[]) => savePreference({ overview_layout: next })
  const missing = (Object.keys(WIDGETS) as WidgetId[]).filter((id) => !layout.some((w) => w.id === id))

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 150, tolerance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )
  const onDragEnd = ({ active, over }: DragEndEvent) => {
    if (!over || active.id === over.id) return
    const from = layout.findIndex((w) => w.id === active.id)
    const to = layout.findIndex((w) => w.id === over.id)
    save(arrayMove(layout, from, to))
  }

  const data: OverviewData = { applications, events, profile, aiEnabled: ai.enabled, day, setDay }
  const firstName = profile?.full_name?.split(" ")[0]

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">{t("overview.title")}</h1>
          <p className="text-sm text-muted-foreground">
            {editing ? t("overview.edit.intro") : firstName ? t("overview.greeting", { name: firstName }) : t("overview.intro")}
          </p>
        </div>
        {editing ? (
          <div className="flex gap-2">
            <Button variant="ghost" size="sm" onClick={() => savePreference({ reset_overview: true })}>
              <RotateCcw />{t("overview.edit.reset")}
            </Button>
            <Button size="sm" onClick={() => setEditing(false)}><Check />{t("overview.edit.done")}</Button>
          </div>
        ) : (
          <Button variant="outline" size="icon" onClick={() => setEditing(true)}
            title={t("overview.edit.start")} aria-label={t("overview.edit.start")}>
            <Paintbrush />
          </Button>
        )}
      </div>

      <ErrorText error={error} />
      {isLoading ? <p className="text-sm text-muted-foreground">{t("common.loading")}</p> : (
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
          <SortableContext items={layout.map((w) => w.id)} strategy={rectSortingStrategy}>
            <div className={cn("grid gap-5 lg:grid-cols-2", editing && "gap-y-14 pt-10")}>
              {layout.map((widget) => (
                <WidgetSlot key={widget.id} widget={widget} data={data} editing={editing}
                  onResize={() => save(layout.map((w) => w.id === widget.id
                    ? { ...w, size: w.size === "full" ? "half" : "full" } : w))}
                  onRemove={() => save(layout.filter((w) => w.id !== widget.id))} />
              ))}
              {editing && <AddWidget missing={missing} onAdd={(id) => save([...layout, { id, size: WIDGETS[id].size }])} />}
            </div>
          </SortableContext>
          {!editing && layout.length === 0 && (
            <div className="rounded-xl border border-dashed p-10 text-center text-sm text-muted-foreground">
              {t("overview.edit.empty")}
            </div>
          )}
        </DndContext>
      )}
    </div>
  )
}
