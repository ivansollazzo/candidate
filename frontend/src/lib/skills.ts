import type { SkillLevel } from "./api"
import { t } from "./i18n"

/** Same scale the backend uses for extraction (app/services/extraction.py). */
export const SKILL_LEVELS: SkillLevel[] = [1, 2, 3, 4]

export const levelLabel = (level: SkillLevel) => t(`level.${level}`)
export const levelDescription = (level: SkillLevel) => t(`level.${level}.description`)
