import { useMutation, useQueryClient } from "@tanstack/react-query"
import { ImageUp, Trash2 } from "lucide-react"
import { useRef } from "react"

import { Avatar } from "@/components/Avatar"
import { ErrorText } from "@/components/ErrorText"
import { Button } from "@/components/ui/button"
import { api } from "@/lib/api"
import { useCurrentUser } from "@/lib/auth"
import { useT } from "@/lib/i18n"

/** Current user's profile photo; upload and removal take effect immediately. */
export function ProfilePhoto() {
  const t = useT()
  const me = useCurrentUser()
  const queryClient = useQueryClient()
  const input = useRef<HTMLInputElement>(null)
  const change = useMutation({
    mutationFn: (file: File | null) => (file ? api.uploadAvatar(file) : api.deleteAvatar()),
    onSuccess: (user) => queryClient.setQueryData(["me"], user),
  })
  if (!me) return null
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-4">
        <Avatar user={me} className="size-16 text-xl" />
        <input ref={input} type="file" accept="image/jpeg,image/png,image/webp,image/gif" hidden
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) change.mutate(file)
            e.target.value = ""
          }} />
        <Button type="button" variant="outline" size="sm" disabled={change.isPending} onClick={() => input.current?.click()}>
          <ImageUp />{t(me.has_avatar ? "profile.photoChange" : "profile.photoUpload")}
        </Button>
        {me.has_avatar && (
          <Button type="button" variant="ghost" size="sm" disabled={change.isPending} onClick={() => change.mutate(null)}>
            <Trash2 />{t("common.remove")}
          </Button>
        )}
      </div>
      <p className="text-xs text-muted-foreground">{t("profile.photoHint")}</p>
      <ErrorText error={change.error} />
    </div>
  )
}
