import { useMutation, useQueryClient } from "@tanstack/react-query"
import { FileText, Loader2, Paperclip, Trash2 } from "lucide-react"
import { useRef, useState } from "react"

import { type Application, applicationsApi, type Attachment } from "@/features/applications/api"
import { ErrorText } from "@/shared/components/ErrorText"
import { getLocale, useT } from "@/shared/lib/i18n"
import { Button } from "@/shared/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card"

function formatSize(bytes: number): string {
  const format = (n: number) => n.toLocaleString(getLocale(), { maximumFractionDigits: 1 })
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${format(bytes / 1024)} KB`
  return `${format(bytes / 1024 / 1024)} MB`
}

/** Files attached to an application; they are deleted together with it. */
export function Attachments({ application }: { application: Application }) {
  const t = useT()
  const queryClient = useQueryClient()
  const input = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const onSaved = (data: Application) => queryClient.setQueryData(["application", application.id], data)
  const add = useMutation({ mutationFn: (files: File[]) => applicationsApi.addAttachments(application.id, files), onSuccess: onSaved })
  const remove = useMutation({
    mutationFn: (attachment: Attachment) => applicationsApi.deleteAttachment(application.id, attachment.id),
    onSuccess: onSaved,
  })
  const upload = (files: FileList | null) => {
    if (files?.length) add.mutate([...files])
  }

  return (
    <Card
      className={dragging ? "ring-2 ring-primary" : undefined}
      onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
      onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragging(false) }}
      onDrop={(e) => { e.preventDefault(); setDragging(false); upload(e.dataTransfer.files) }}
    >
      <CardHeader>
        <CardTitle>{t("attachments.title")}</CardTitle>
        <input ref={input} type="file" multiple hidden
          onChange={(e) => { upload(e.target.files); e.target.value = "" }} />
        <Button variant="outline" size="sm" disabled={add.isPending} onClick={() => input.current?.click()}>
          {add.isPending ? <Loader2 className="animate-spin" /> : <Paperclip />}{t("attachments.add")}
        </Button>
      </CardHeader>
      <CardContent className="space-y-3">
        {application.attachments.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("attachments.empty")}</p>
        ) : (
          <ul className="divide-y">
            {application.attachments.map((attachment) => (
              <li key={attachment.id} className="flex items-center gap-3 py-2">
                <FileText className="size-4 shrink-0 text-muted-foreground" />
                <a href={`/api/applications/${application.id}/attachments/${attachment.id}`} download={attachment.filename}
                  className="min-w-0 flex-1 truncate text-sm hover:underline" title={attachment.filename}>
                  {attachment.filename}
                </a>
                <span className="shrink-0 text-xs text-muted-foreground">{formatSize(attachment.size)}</span>
                <Button variant="ghost" size="icon" aria-label={t("common.delete")} disabled={remove.isPending}
                  onClick={() => { if (confirm(t("attachments.confirmDelete", { name: attachment.filename }))) remove.mutate(attachment) }}>
                  <Trash2 />
                </Button>
              </li>
            ))}
          </ul>
        )}
        <p className="text-xs text-muted-foreground">{t("attachments.hint")}</p>
        <ErrorText error={add.error ?? remove.error} />
      </CardContent>
    </Card>
  )
}
