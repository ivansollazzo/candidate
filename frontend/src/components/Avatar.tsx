import { useState } from "react"

import type { User } from "@/lib/api"
import { avatarUrl, useCurrentUser } from "@/lib/auth"
import { cn } from "@/lib/utils"

/** Profile photo, or the username's initial when there is none. */
export function Avatar({ user, className }: { user: User; className?: string }) {
  const viewer = useCurrentUser()
  const url = user.has_avatar ? avatarUrl(user, viewer) : null
  const [failed, setFailed] = useState<string | null>(null)
  return url && failed !== url ? (
    <img src={url} alt="" onError={() => setFailed(url)}
      className={cn("size-7 shrink-0 rounded-full object-cover", className)} />
  ) : (
    <span aria-hidden className={cn("flex size-7 shrink-0 items-center justify-center rounded-full bg-secondary text-xs font-semibold uppercase text-muted-foreground", className)}>
      {user.username[0]}
    </span>
  )
}
