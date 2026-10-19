import { type FormEvent, useState } from "react"

import { ErrorText } from "@/components/ErrorText"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Field } from "@/components/ui/input"
import { Switch } from "@/components/ui/switch"
import type { Settings } from "@/lib/api"
import { type MessageKey, useT } from "@/lib/i18n"
import { useUpdateSettings } from "@/lib/settings"

const POLICY_KEYS = ["password_min_length", "password_require_uppercase", "password_require_digit",
  "password_require_symbol", "session_hours", "max_login_attempts", "lockout_minutes"] as const
type Policy = Pick<Settings, (typeof POLICY_KEYS)[number]>

const pick = (settings: Settings) => Object.fromEntries(POLICY_KEYS.map((k) => [k, settings[k]])) as Policy

const NUMBERS: { key: keyof Policy; label: MessageKey; hint: MessageKey; min: number; max: number }[] = [
  { key: "password_min_length", label: "security.minLength", hint: "security.minLengthHint", min: 8, max: 128 },
  { key: "session_hours", label: "security.sessionHours", hint: "security.sessionHoursHint", min: 1, max: 720 },
  { key: "max_login_attempts", label: "security.attempts", hint: "security.attemptsHint", min: 0, max: 100 },
  { key: "lockout_minutes", label: "security.lockout", hint: "security.lockoutHint", min: 1, max: 1440 },
]

const RULES: { key: keyof Policy; label: MessageKey }[] = [
  { key: "password_require_uppercase", label: "security.uppercase" },
  { key: "password_require_digit", label: "security.digit" },
  { key: "password_require_symbol", label: "security.symbol" },
]

/** Password, session and login-attempt policies (admin only). */
export function SecurityTab({ settings }: { settings: Settings }) {
  const t = useT()
  const update = useUpdateSettings()
  const [policy, setPolicy] = useState(() => pick(settings))
  const changed = POLICY_KEYS.some((k) => policy[k] !== settings[k])
  const valid = NUMBERS.every(({ key, min, max }) => {
    const value = policy[key] as number
    return Number.isInteger(value) && value >= min && value <= max
  })
  const set = (changes: Partial<Policy>) => setPolicy({ ...policy, ...changes })
  const submit = (e: FormEvent) => {
    e.preventDefault()
    update.mutate(policy)
  }

  return (
    <form onSubmit={submit} className="space-y-5">
      <Card>
        <CardHeader><CardTitle>{t("security.passwords")}</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <ul className="divide-y rounded-lg border">
            {RULES.map(({ key, label }) => (
              <li key={key} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
                {t(label)}
                <Switch label={t(label)} checked={policy[key] as boolean} onChange={(value) => set({ [key]: value })} />
              </li>
            ))}
          </ul>
          <p className="text-xs text-muted-foreground">{t("security.passwordsHint")}</p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>{t("security.access")}</CardTitle></CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          {NUMBERS.map(({ key, label, hint, min, max }) => (
            <div key={key}>
              <Field label={t(label)} type="number" min={min} max={max} required value={policy[key] as number}
                onChange={(e) => set({ [key]: e.target.valueAsNumber })} />
              <p className="mt-1 text-xs text-muted-foreground">{t(hint)}</p>
            </div>
          ))}
        </CardContent>
      </Card>
      <ErrorText error={update.error} />
      {update.isSuccess && !changed && <p className="text-sm text-emerald-700 dark:text-emerald-400">{t("security.saved")}</p>}
      <Button type="submit" disabled={!changed || !valid || update.isPending}>{t("common.save")}</Button>
    </form>
  )
}
