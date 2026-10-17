import { Check, Pencil, Plus, Trash2 } from "lucide-react"
import { type ReactNode, useState } from "react"

import { Button } from "@/components/ui/button"
import { Input, Label, Textarea } from "@/components/ui/input"
import { useT } from "@/lib/i18n"
import { cn } from "@/lib/utils"

export type FieldDef = {
  key: string
  label: string
  type?: "text" | "textarea" | "date" | "checkbox" | "list"
  placeholder?: string
  wide?: boolean
}

/** Editable list of entries (experience, education, projects...). */
export function EntryList<T extends object>({ items, onChange, fields, render, empty, addLabel, blank }: {
  items: T[]
  onChange: (items: T[]) => void
  fields: FieldDef[]
  render: (item: T) => ReactNode
  empty: string
  addLabel: string
  blank: T
}) {
  const t = useT()
  const [editing, setEditing] = useState<number | null>(null)
  const update = (index: number, key: string, value: unknown) =>
    onChange(items.map((item, i) => (i === index ? { ...item, [key]: value } : item)))
  const remove = (index: number) => {
    onChange(items.filter((_, i) => i !== index))
    setEditing(null)
  }

  return (
    <div className="space-y-2">
      {items.length === 0 && <p className="text-sm text-muted-foreground">{empty}</p>}
      {items.map((item, index) => (
        <div key={index} className={cn("group rounded-lg border p-3", editing === index && "bg-secondary/40")}>
          {editing === index ? (
            <div className="space-y-3">
              <div className="grid gap-2 sm:grid-cols-2">
                {fields.map((field) => (
                  <FieldInput key={field.key} field={field} value={(item as Record<string, unknown>)[field.key]}
                    onChange={(value) => update(index, field.key, value)} />
                ))}
              </div>
              <div className="flex justify-between">
                <Button variant="ghost" size="sm" className="text-red-600 dark:text-red-400" onClick={() => remove(index)}>
                  <Trash2 />{t("common.delete")}
                </Button>
                <Button variant="outline" size="sm" onClick={() => setEditing(null)}><Check />{t("common.done")}</Button>
              </div>
            </div>
          ) : (
            <div className="flex items-start gap-2">
              <div className="min-w-0 flex-1 text-sm">{render(item)}</div>
              <div className="flex opacity-60 group-hover:opacity-100">
                <Button variant="ghost" size="icon" aria-label={t("common.edit")} onClick={() => setEditing(index)}><Pencil /></Button>
                <Button variant="ghost" size="icon" aria-label={t("common.delete")} onClick={() => remove(index)}><Trash2 /></Button>
              </div>
            </div>
          )}
        </div>
      ))}
      <Button variant="outline" size="sm" onClick={() => { onChange([...items, { ...blank }]); setEditing(items.length) }}>
        <Plus />{addLabel}
      </Button>
    </div>
  )
}

function FieldInput({ field, value, onChange }: { field: FieldDef; value: unknown; onChange: (value: unknown) => void }) {
  const t = useT()
  const wide = field.wide || field.type === "textarea"
  if (field.type === "checkbox") {
    return (
      <label className="flex items-center gap-2 self-end pb-2 text-sm">
        <input type="checkbox" checked={Boolean(value)} onChange={(e) => onChange(e.target.checked)} />
        {field.label}
      </label>
    )
  }
  const text = field.type === "list" ? ((value as string[] | undefined) ?? []).join(", ") : ((value as string | null) ?? "")
  const set = (raw: string) =>
    onChange(field.type === "list" ? raw.split(",").map((v) => v.trim()).filter(Boolean) : raw || null)
  return (
    <div className={cn(wide && "sm:col-span-2")}>
      <Label className="mb-1 block">{field.label}</Label>
      {field.type === "textarea" ? (
        <Textarea value={text} placeholder={field.placeholder} onChange={(e) => set(e.target.value)} />
      ) : (
        <Input value={text}
          placeholder={field.placeholder ?? (field.type === "date" ? t("entry.datePlaceholder") : field.type === "list" ? t("entry.listPlaceholder") : undefined)}
          onChange={(e) => (field.type === "list" ? onChange(e.target.value.split(",").map((v) => v.trimStart())) : set(e.target.value))}
          onBlur={(e) => set(e.target.value)} />
      )}
    </div>
  )
}
