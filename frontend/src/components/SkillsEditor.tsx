import { Check, Pencil, Plus, X } from "lucide-react"
import { useState } from "react"

import { SkillLevelDots } from "@/components/SkillLevelDots"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import type { ProfileSkill, SkillLevel } from "@/lib/api"
import { useT } from "@/lib/i18n"
import { levelDescription, levelLabel, SKILL_LEVELS } from "@/lib/skills"

// Group for uncategorized skills
const OTHER = ""

/** Skill editor: name, category and level are applied on "Done". */
function SkillForm({ skill, taken, onSave, onCancel }: {
  skill: ProfileSkill
  /** True if another skill already has this name */
  taken: (name: string) => boolean
  onSave: (skill: ProfileSkill) => void
  onCancel: () => void
}) {
  const t = useT()
  const [name, setName] = useState(skill.name)
  const [category, setCategory] = useState(skill.category ?? "")
  const [level, setLevel] = useState(skill.level)
  const clash = name.trim().toLowerCase() !== skill.name.toLowerCase() && taken(name.trim())
  const save = () => {
    if (!name.trim() || clash) return
    onSave({ ...skill, name: name.trim(), category: category.trim() || null, level })
  }
  return (
    <div className="space-y-2 rounded-md bg-secondary/40 p-2">
      <div className="flex flex-wrap items-center gap-2">
        <Input className="h-8 min-w-40 flex-1" aria-label={t("skills.name")} value={name} autoFocus aria-invalid={clash}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); save() } }} />
        <Input className="h-8 w-36" placeholder={t("skills.category")} aria-label={t("skills.category")}
          list="skill-categories" value={category} onChange={(e) => setCategory(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); save() } }} />
        <SkillLevelDots level={level} onChange={setLevel} />
      </div>
      {clash && <p className="text-xs text-red-600 dark:text-red-400">{t("skills.duplicate")}</p>}
      {skill.evidence && <p className="text-xs text-muted-foreground">{skill.evidence}</p>}
      <div className="flex gap-2">
        <Button type="button" size="sm" disabled={!name.trim() || clash} onClick={save}><Check />{t("common.done")}</Button>
        <Button type="button" size="sm" variant="ghost" onClick={onCancel}>{t("common.cancel")}</Button>
      </div>
    </div>
  )
}

/**
 * Profile skills grouped by category: the list shows name and level, the pencil edits the rest.
 * `onRemove` and `onRename` also update projects and experience entries that reference the skill.
 */
export function SkillsEditor({ skills, onChange, onRemove, onRename }: {
  skills: ProfileSkill[]
  onChange: (skills: ProfileSkill[]) => void
  onRemove: (name: string) => void
  onRename: (from: string, skill: ProfileSkill) => void
}) {
  const t = useT()
  const [editing, setEditing] = useState<string | null>(null)
  const taken = (name: string) => skills.some((s) => s.name.toLowerCase() === name.toLowerCase())
  const [draft, setDraft] = useState<{ name: string; category: string; level: SkillLevel }>({ name: "", category: "", level: 2 })
  const groups = new Map<string, ProfileSkill[]>()
  for (const skill of skills) {
    const key = skill.category || OTHER
    groups.set(key, [...(groups.get(key) ?? []), skill])
  }
  const save = (name: string, skill: ProfileSkill) => {
    if (skill.name !== name) onRename(name, skill)
    else onChange(skills.map((s) => (s.name === name ? skill : s)))
    setEditing(null)
  }
  const unrated = skills.filter((s) => s.level == null).length
  const add = () => {
    const name = draft.name.trim()
    if (!name || taken(name)) return
    onChange([...skills, { name, category: draft.category.trim() || null, level: draft.level, evidence: null }])
    setDraft({ ...draft, name: "" })
  }

  return (
    <div className="space-y-5">
      <details className="rounded-lg bg-secondary/60 px-3 py-2 text-sm">
        <summary className="cursor-pointer text-muted-foreground">{t("skills.howToRead")}</summary>
        <ul className="mt-2 space-y-1">
          {SKILL_LEVELS.map((l) => (
            <li key={l} className="flex items-center gap-2">
              <SkillLevelDots level={l} />
              <span className="w-24 font-medium">{levelLabel(l)}</span>
              <span className="text-muted-foreground">{levelDescription(l)}</span>
            </li>
          ))}
        </ul>
      </details>

      {skills.length === 0 && <p className="text-sm text-muted-foreground">{t("skills.none")}</p>}
      {unrated > 0 && (
        <p className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
          {t("skills.unrated", { count: unrated })}
        </p>
      )}
      <div className="grid gap-x-8 gap-y-5 md:grid-cols-2">
        {[...groups.entries()].map(([category, items]) => (
          <div key={category}>
            <h4 className="mb-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">{category || t("skills.other")}</h4>
            <ul className="divide-y">
              {items.map((skill) => (
                <li key={skill.name} className="py-1.5 text-sm">
                  {editing === skill.name ? (
                    <SkillForm skill={skill} taken={taken} onSave={(updated) => save(skill.name, updated)}
                      onCancel={() => setEditing(null)} />
                  ) : (
                    <div className="group flex items-center gap-3">
                      <span className="min-w-0 flex-1">
                        <span className="font-medium">{skill.name}</span>
                        {skill.level == null && (
                          <span className="block text-xs text-amber-700 dark:text-amber-400">{t("skills.setLevel")}</span>
                        )}
                      </span>
                      <SkillLevelDots level={skill.level} />
                      <span className="flex">
                        <button type="button" className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
                          aria-label={t("skills.editItem", { name: skill.name })} title={t("common.edit")}
                          onClick={() => setEditing(skill.name)}>
                          <Pencil className="size-3.5" />
                        </button>
                        <button type="button" className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
                          aria-label={t("common.removeItem", { name: skill.name })} title={t("skills.removeHint")}
                          onClick={() => onRemove(skill.name)}>
                          <X className="size-3.5" />
                        </button>
                      </span>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-2 border-t pt-4">
        <Input className="h-8 w-48" placeholder={t("skills.new")} value={draft.name}
          onChange={(e) => setDraft({ ...draft, name: e.target.value })}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add() } }} />
        <Input className="h-8 w-48" placeholder={t("skills.category")} list="skill-categories" value={draft.category}
          onChange={(e) => setDraft({ ...draft, category: e.target.value })} />
        <datalist id="skill-categories">
          {[...groups.keys()].filter((c) => c !== OTHER).map((c) => <option key={c} value={c} />)}
        </datalist>
        <SkillLevelDots level={draft.level} onChange={(level) => setDraft({ ...draft, level })} />
        <Button variant="outline" size="sm" onClick={add}><Plus />{t("common.add")}</Button>
      </div>
    </div>
  )
}
