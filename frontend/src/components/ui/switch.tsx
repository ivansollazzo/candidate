import { cn } from "@/lib/utils"

export function Switch({ checked, disabled, onChange, label }: {
  checked: boolean
  disabled?: boolean
  onChange: (value: boolean) => void
  label: string
}) {
  return (
    <button type="button" role="switch" aria-checked={checked} aria-label={label} disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn("relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors disabled:opacity-50",
        checked ? "bg-emerald-500" : "bg-input")}>
      <span className={cn("inline-block size-5 rounded-full bg-white shadow transition-transform",
        checked ? "translate-x-5.5" : "translate-x-0.5")} />
    </button>
  )
}
