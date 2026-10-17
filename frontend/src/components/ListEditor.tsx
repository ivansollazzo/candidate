import { Plus, X } from "lucide-react"
import { useState } from "react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useT } from "@/lib/i18n"

/** Editable list of strings (requirements, benefits...). */
export function ListEditor({ items, onChange, placeholder }: {
  items: string[]
  onChange: (items: string[]) => void
  placeholder?: string
}) {
  const t = useT()
  const [draft, setDraft] = useState("")
  const add = () => {
    const value = draft.trim()
    if (!value) return
    onChange([...items, value])
    setDraft("")
  }
  return (
    <div className="space-y-1.5">
      {items.map((item, i) => (
        <div key={i} className="group flex items-start gap-2 text-sm">
          <span className="mt-2 size-1.5 shrink-0 rounded-full bg-muted-foreground/50" />
          <Input
            value={item}
            className="h-8 border-transparent shadow-none hover:border-input"
            onChange={(e) => onChange(items.map((v, j) => (j === i ? e.target.value : v)))}
          />
          <Button variant="ghost" size="icon" className="opacity-0 group-hover:opacity-100" aria-label={t("common.remove")}
            onClick={() => onChange(items.filter((_, j) => j !== i))}>
            <X />
          </Button>
        </div>
      ))}
      <div className="flex gap-2">
        <Input value={draft} placeholder={placeholder ?? t("common.addItem")} className="h-8"
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add() } }} />
        <Button variant="outline" size="icon" onClick={add} aria-label={t("common.add")}><Plus /></Button>
      </div>
    </div>
  )
}
