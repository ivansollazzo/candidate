import { Monitor, Moon, Sun } from "lucide-react"

import { LanguageSelect } from "@/components/LanguageSelect"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useCurrentUser, useUpdateMe } from "@/lib/auth"
import { useT } from "@/lib/i18n"
import { THEMES } from "@/lib/theme"
import { cn } from "@/lib/utils"

const THEME_ICONS = { light: Sun, dark: Moon, system: Monitor }

/** Language and theme (per-user preferences). */
export function AppearanceTab() {
  const t = useT()
  const me = useCurrentUser()
  const update = useUpdateMe()

  return (
    <>
      {update.error && <p className="text-sm text-red-600 dark:text-red-400">{update.error.message}</p>}
      <Card>
        <CardHeader>
          <CardTitle>{t("settings.language")}</CardTitle>
          <LanguageSelect className="w-40" value={me?.language} disabled={update.isPending}
            onChange={(language) => update.mutate({ language })} />
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">{t("settings.languageHint")}</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex-wrap">
          <CardTitle>{t("settings.theme")}</CardTitle>
          <div className="inline-flex rounded-md border p-0.5" role="radiogroup" aria-label={t("settings.theme")}>
            {THEMES.map((theme) => {
              const Icon = THEME_ICONS[theme]
              return (
                <button key={theme} type="button" role="radio" aria-checked={me?.theme === theme}
                  disabled={update.isPending} onClick={() => update.mutate({ theme })}
                  className={cn("flex items-center gap-1.5 rounded px-3 py-1 text-sm text-muted-foreground hover:text-foreground",
                    me?.theme === theme && "bg-secondary text-foreground")}>
                  <Icon className="size-4" />{t(`theme.${theme}`)}
                </button>
              )
            })}
          </div>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">{t("settings.themeHint")}</p>
        </CardContent>
      </Card>
    </>
  )
}
