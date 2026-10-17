import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Label, Select } from "@/components/ui/input"
import { Switch } from "@/components/ui/switch"
import { ACCELERATOR_NAMES, useAiStatus, useHealth } from "@/lib/ai"
import { ACCELERATORS, type HardwareStatus, type Settings } from "@/lib/api"
import { useT } from "@/lib/i18n"
import { useSettings, useUpdateSettings } from "@/lib/settings"
import { cn } from "@/lib/utils"

const HARDWARE_TONES: Record<HardwareStatus, string> = {
  available: "bg-emerald-500",
  unavailable: "bg-slate-300 dark:bg-slate-600",
  failed: "bg-amber-500",
}

/** AI features and hardware acceleration (admin only). */
export function SystemTab() {
  const t = useT()
  const ai = useAiStatus()
  const settings = useSettings()
  const { data: health } = useHealth()
  const update = useUpdateSettings()
  const hardware = health?.llm.hardware
  const inUse = ai.ready ? health?.llm.accelerator : null

  return (
    <>
      {update.error && <p className="text-sm text-red-600 dark:text-red-400">{update.error.message}</p>}
      <Card>
        <CardHeader>
          <CardTitle>{t("settings.ai")}</CardTitle>
          <Switch label={t("settings.aiToggle")} checked={settings?.llm_enabled ?? false}
            disabled={!settings || update.isPending} onChange={(llm_enabled) => update.mutate({ llm_enabled })} />
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <p className="flex items-center gap-2">
            <span className={cn("size-2 rounded-full", ai.tone)} />
            {ai.label}
          </p>
          <p className="text-muted-foreground">{t("settings.aiText")}</p>
          <p className="text-muted-foreground">{t("settings.aiMemory")}</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>{t("settings.hardware")}</CardTitle></CardHeader>
        <CardContent className="space-y-4 text-sm">
          <p className="text-muted-foreground">{t("settings.hardwareHint")}</p>
          {hardware ? (
            <ul className="divide-y rounded-lg border">
              {ACCELERATORS.map((stack) => (
                <li key={stack} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2">
                  <span className="w-16 font-medium">{ACCELERATOR_NAMES[stack]}</span>
                  <span className="text-muted-foreground">{t(`hardware.${stack}`)}</span>
                  <span className="ml-auto flex items-center gap-2">
                    {inUse === stack && (
                      <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200">
                        {t("hardware.inUse")}
                      </span>
                    )}
                    <span className={cn("size-2 rounded-full", HARDWARE_TONES[hardware[stack]])} />
                    {t(`hardware.${hardware[stack]}`)}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted-foreground">{t("settings.hardwarePending")}</p>
          )}
          <div>
            <Label className="mb-1 block">{t("settings.accelerator")}</Label>
            <Select className="w-72" value={settings?.llm_accelerator} disabled={!settings || update.isPending}
              onChange={(e) => update.mutate({ llm_accelerator: e.target.value as Settings["llm_accelerator"] })}>
              <option value="auto">{t("settings.auto")}</option>
              {ACCELERATORS.map((stack) => (
                <option key={stack} value={stack}
                  disabled={hardware?.[stack] !== "available" && settings?.llm_accelerator !== stack}>
                  {ACCELERATOR_NAMES[stack]} · {t(`hardware.${stack}`)}
                </option>
              ))}
            </Select>
            <p className="mt-1 text-xs text-muted-foreground">{t("settings.acceleratorHint")}</p>
          </div>
        </CardContent>
      </Card>
    </>
  )
}
