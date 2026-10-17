import { Plus, X } from "lucide-react"
import { useState } from "react"

import { Button } from "@/components/ui/button"
import { Input, Select } from "@/components/ui/input"
import { useT } from "@/lib/i18n"
import { cn } from "@/lib/utils"

type Chip = { name: string; tag?: string | null }

/** Skills as chips, with an optional label (importance or level). */
export function SkillChips({ skills, onChange, tags, defaultTag }: {
  skills: Chip[]
  onChange: (skills: Chip[]) => void
  tags: { value: string; label: string }[]
  defaultTag?: string
}) {
  const t = useT()
  const [name, setName] = useState("")
  const [tag, setTag] = useState(defaultTag ?? "")
  const add = () => {
    const value = name.trim()
    if (!value || skills.some((s) => s.name.toLowerCase() === value.toLowerCase())) return
    onChange([...skills, { name: value, tag: tag || null }])
    setName("")
  }
  const label = (value?: string | null) => tags.find((tag) => tag.value === value)?.label

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-1.5">
        {skills.length === 0 && <span className="text-sm text-muted-foreground">{t("skills.none")}</span>}
        {skills.map((s) => (
          <span key={s.name}
            className={cn("inline-flex items-center gap-1 rounded-full border py-0.5 pl-2.5 pr-1 text-sm",
              s.tag === "nice_to_have" && "border-dashed")}>
            {s.name}
            {label(s.tag) && <span className="text-xs text-muted-foreground">· {label(s.tag)}</span>}
            <button className="rounded-full p-0.5 text-muted-foreground hover:bg-accent hover:text-foreground"
              aria-label={t("common.removeItem", { name: s.name })} onClick={() => onChange(skills.filter((x) => x.name !== s.name))}>
              <X className="size-3" />
            </button>
          </span>
        ))}
      </div>
      <div className="flex gap-2">
        <Input value={name} placeholder={t("skills.new")} className="h-8"
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add() } }} />
        <Select value={tag} onChange={(e) => setTag(e.target.value)} className="h-8 w-40">
          {!defaultTag && <option value="">—</option>}
          {tags.map((tag) => <option key={tag.value} value={tag.value}>{tag.label}</option>)}
        </Select>
        <Button variant="outline" size="icon" onClick={add} aria-label={t("skills.add")}><Plus /></Button>
      </div>
    </div>
  )
}
