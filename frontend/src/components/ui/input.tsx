import { type ComponentProps, useId } from "react"

import { cn } from "@/lib/utils"

const base =
  "w-full rounded-md border border-input bg-transparent px-3 text-sm shadow-xs placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"

export function Input({ className, ...props }: ComponentProps<"input">) {
  return <input className={cn(base, "h-9 py-1", className)} {...props} />
}

export function Textarea({ className, ...props }: ComponentProps<"textarea">) {
  return <textarea className={cn(base, "min-h-20 py-2", className)} {...props} />
}

export function Select({ className, ...props }: ComponentProps<"select">) {
  return <select className={cn(base, "h-9 py-1 bg-card", className)} {...props} />
}

export function Label({ className, ...props }: ComponentProps<"label">) {
  return <label className={cn("text-xs font-medium text-muted-foreground", className)} {...props} />
}

/** Text input with its label. */
export function Field({ label, ...props }: ComponentProps<"input"> & { label: string }) {
  const id = useId()
  return (
    <div>
      <Label htmlFor={id} className="mb-1 block">{label}</Label>
      <Input id={id} {...props} />
    </div>
  )
}
