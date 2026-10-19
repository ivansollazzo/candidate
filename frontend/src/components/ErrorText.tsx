import { cn } from "@/lib/utils"

/** Error message from a failed request (or a plain text); renders nothing without an error. */
export function ErrorText({ error, className }: { error: Error | string | null | undefined; className?: string }) {
  if (!error) return null
  return (
    <p className={cn("text-sm text-red-600 dark:text-red-400", className)}>
      {typeof error === "string" ? error : error.message}
    </p>
  )
}
