import { Check, X } from "lucide-react"
import { useId } from "react"

import { Input, Label } from "@/components/ui/input"
import type { PasswordPolicy } from "@/lib/api"
import { passwordProblems } from "@/lib/auth"
import { useT } from "@/lib/i18n"
import { cn } from "@/lib/utils"

/** New password with confirmation and the policy rules still unmet. */
export function NewPassword({ value, confirm, onChange, onConfirmChange, policy, label }: {
  value: string
  confirm: string
  onChange: (value: string) => void
  onConfirmChange: (value: string) => void
  policy: PasswordPolicy | undefined
  label?: string
}) {
  const t = useT()
  const id = useId()
  const problems = policy ? passwordProblems(value, policy) : []
  const mismatch = confirm !== "" && confirm !== value
  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <Label htmlFor={`${id}-new`} className="mb-1 block">{label ?? t("password.new")}</Label>
          <Input id={`${id}-new`} type="password" autoComplete="new-password" value={value}
            onChange={(e) => onChange(e.target.value)} />
        </div>
        <div>
          <Label htmlFor={`${id}-confirm`} className="mb-1 block">{t("password.confirm")}</Label>
          <Input id={`${id}-confirm`} type="password" autoComplete="new-password" value={confirm}
            aria-invalid={mismatch} onChange={(e) => onConfirmChange(e.target.value)} />
        </div>
      </div>
      {value !== "" && (
        <p className={cn("flex items-center gap-1.5 text-xs",
          problems.length || mismatch ? "text-muted-foreground" : "text-emerald-700 dark:text-emerald-400")}>
          {problems.length || mismatch ? <X className="size-3.5" /> : <Check className="size-3.5" />}
          {problems.length ? t("password.needs", { rules: problems.join(", ") })
            : mismatch ? t("password.mismatch") : t("password.ok")}
        </p>
      )}
    </div>
  )
}

/** True when the new password meets the policy and is confirmed. */
export const isPasswordValid = (value: string, confirm: string, policy: PasswordPolicy | undefined) =>
  !!policy && value === confirm && passwordProblems(value, policy).length === 0
