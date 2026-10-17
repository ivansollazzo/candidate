import type { SkillLevel } from "@/lib/api"
import { useT } from "@/lib/i18n"
import { levelDescription, levelLabel, SKILL_LEVELS } from "@/lib/skills"
import { cn } from "@/lib/utils"

/** Level 1-4 as dots; clickable when `onChange` is given. */
export function SkillLevelDots({ level, onChange, className }: {
  level: SkillLevel | null | undefined
  onChange?: (level: SkillLevel) => void
  className?: string
}) {
  const t = useT()
  const describe = (l: SkillLevel) => `${levelLabel(l)}: ${levelDescription(l)}`
  return (
    <span className={cn("inline-flex items-center gap-0.5", className)}
      title={level != null ? describe(level) : t("level.unknown")}>
      {SKILL_LEVELS.map((l) => {
        const filled = level != null && l <= level
        const dot = <span className={cn("block size-2 rounded-full", filled ? "bg-foreground" : "bg-muted-foreground/25")} />
        return onChange ? (
          <button key={l} type="button" className="p-0.5" aria-label={t("level.aria", { label: levelLabel(l) })}
            title={describe(l)} onClick={() => onChange(l)}>
            {dot}
          </button>
        ) : <span key={l} className="p-0.5">{dot}</span>
      })}
    </span>
  )
}
