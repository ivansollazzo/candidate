import { CircleAlert, Download, Loader2, Lock, Plus, Trash2, Upload, X } from "lucide-react"
import { type FormEvent, type KeyboardEvent, useState } from "react"

import { ErrorText } from "@/components/ErrorText"
import { Failure } from "@/components/settings/UpdatesTab"
import { Button, buttonVariants } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input, Label } from "@/components/ui/input"
import { type Https, HTTPS_AUTHORITY_URL, type HttpsMode } from "@/lib/api"
import { useDeleteCertificate, useHttps, useSaveHttps, useUploadCertificate } from "@/lib/https"
import { dateLocale, type MessageKey, useT } from "@/lib/i18n"
import { cn } from "@/lib/utils"

const MODES: { value: HttpsMode; label: MessageKey; hint: MessageKey }[] = [
  { value: "off", label: "https.modeOff", hint: "https.modeOffHint" },
  { value: "internal", label: "https.modeInternal", hint: "https.modeInternalHint" },
  { value: "custom", label: "https.modeCustom", hint: "https.modeCustomHint" },
]

const STATES: Record<Https["state"], { label: MessageKey; color: string }> = {
  off: { label: "https.stateOff", color: "bg-muted-foreground/50" },
  active: { label: "https.stateActive", color: "bg-emerald-500" },
  applying: { label: "https.stateApplying", color: "bg-amber-500" },
  error: { label: "https.stateError", color: "bg-red-500" },
  unknown: { label: "https.stateUnknown", color: "bg-muted-foreground/50" },
}

// The web server checks for a new configuration every 5 seconds
const MOVE_SECONDS = 8

const formatDate = (value: string) => new Date(value).toLocaleDateString(dateLocale(), { dateStyle: "medium" })

/** Lowercase host without brackets, as the backend stores it; light check, the backend has the last word. */
function cleanHost(value: string): string | null {
  const host = value.trim().toLowerCase().replace(/^\[(.*)\]$/, "$1").replace(/\.$/, "")
  if (!host || /[\s/]/.test(host) || /^[^:]+:\d+$/.test(host)) return null
  return host
}

/** Whether the address in the browser bar is one of the hosts (a wildcard covers one label). */
function hostListed(hosts: string[], current: string): boolean {
  const host = current.replace(/^\[(.*)\]$/, "$1").toLowerCase()
  return hosts.some((h) => h === host || (h.startsWith("*.") && host.endsWith(h.slice(1)) &&
    !host.slice(0, -h.length + 1).includes(".")))
}

function siteUrl(host: string, port: number): string {
  const shown = host.includes(":") ? `[${host}]` : host
  return port === 443 ? `https://${shown}` : `https://${shown}:${port}`
}

function HostsEditor({ hosts, onChange }: { hosts: string[]; onChange: (hosts: string[]) => void }) {
  const t = useT()
  const [draft, setDraft] = useState("")
  const [wrong, setWrong] = useState(false)
  const add = () => {
    const values = draft.split(/[,\s]+/).filter(Boolean)
    const cleaned = values.map(cleanHost)
    if (cleaned.some((h) => h == null)) {
      setWrong(true)
      return
    }
    onChange([...hosts, ...(cleaned as string[]).filter((h, i, all) => !hosts.includes(h) && all.indexOf(h) === i)])
    setDraft("")
    setWrong(false)
  }
  const onKey = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      event.preventDefault()
      add()
    }
  }
  return (
    <div className="space-y-2">
      <Label className="block">{t("https.hosts")}</Label>
      {hosts.length > 0 && (
        <ul className="flex flex-wrap gap-1.5">
          {hosts.map((host) => (
            <li key={host} className="flex items-center gap-1 rounded-full border bg-secondary/50 py-0.5 pl-2.5 pr-1 font-mono text-xs">
              {host}
              <button type="button" className="rounded-full p-0.5 text-muted-foreground hover:bg-secondary hover:text-foreground"
                aria-label={t("https.removeHost", { host })} onClick={() => onChange(hosts.filter((h) => h !== host))}>
                <X className="size-3" />
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="flex gap-2">
        <Input value={draft} placeholder="candidate.local, 192.168.1.50" aria-invalid={wrong}
          onChange={(e) => { setDraft(e.target.value); setWrong(false) }} onKeyDown={onKey}
          className={cn("font-mono", wrong && "border-red-500")} />
        <Button type="button" variant="outline" onClick={add} disabled={!draft.trim()}><Plus />{t("https.addHost")}</Button>
      </div>
      <p className={cn("text-xs", wrong ? "text-red-600 dark:text-red-400" : "text-muted-foreground")}>
        {wrong ? t("https.badHost") : t("https.hostsHint")}
      </p>
    </div>
  )
}

function Status({ data }: { data: Https }) {
  const t = useT()
  const state = STATES[data.state]
  const current = window.location.hostname
  const listed = hostListed(data.hosts, current)
  return (
    <div className="space-y-2 text-sm">
      <p className="flex items-center gap-2">
        {data.state === "applying" ? <Loader2 className="size-3 animate-spin text-amber-500" />
          : <span className={cn("size-2 rounded-full", state.color)} />}
        {t(state.label)}
      </p>
      {data.state === "error" && <Failure message={t("https.errorText")} detail={data.error ?? ""} />}
      {data.state === "unknown" && <p className="text-xs text-muted-foreground">{t("https.unknownHint")}</p>}
      {data.state === "active" && !data.secure_request && listed && (
        <a className={buttonVariants({ size: "sm" })} href={siteUrl(current, data.port) + window.location.pathname + window.location.search}>
          <Lock />{t("https.openSecure")}
        </a>
      )}
    </div>
  )
}

function SettingsCard({ data, onMode, moving, onMoving }: {
  data: Https
  onMode: (mode: HttpsMode) => void
  /** Address this page is about to move to after a save */
  moving: string | null
  onMoving: (target: string) => void
}) {
  const t = useT()
  const save = useSaveHttps()
  const [mode, setModeState] = useState<HttpsMode>(data.mode)
  const setMode = (value: HttpsMode) => {
    setModeState(value)
    onMode(value)
  }
  const [hosts, setHosts] = useState<string[]>(data.hosts)
  const changed = mode !== data.mode || JSON.stringify(hosts) !== JSON.stringify(data.hosts)
  const current = window.location.hostname
  // Saving a list without the address in use would leave this browser on a certificate for other names
  const leavesThisAddress = mode !== "off" && hosts.length > 0 && !hostListed(hosts, current)
  // Once the web server switches, this page's address (http:// or https://) stops answering: it moves to the
  // other one by itself, after the few seconds the web server takes to pick up the new configuration
  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    if (leavesThisAddress && !confirm(t("https.confirmNotListed", { host: current }))) return
    save.mutate({ mode, hosts }, {
      onSuccess: (saved) => {
        const path = window.location.pathname + window.location.search
        const target = saved.mode !== "off" && !saved.secure_request && hostListed(saved.hosts, current)
          ? siteUrl(current, saved.port) + path
          : saved.mode === "off" && saved.secure_request ? `http://${window.location.host}${path}` : null
        if (!target) return
        onMoving(target)
        window.setTimeout(() => window.location.assign(target), MOVE_SECONDS * 1000)
      },
    })
  }

  return (
    <Card>
      <CardHeader><CardTitle>{t("https.title")}</CardTitle></CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="space-y-5">
          <Status data={data} />
          <fieldset className="space-y-2">
            <legend className="mb-2 text-xs font-medium text-muted-foreground">{t("https.mode")}</legend>
            {MODES.map((item) => (
              <label key={item.value} className={cn("flex cursor-pointer gap-3 rounded-lg border p-3 text-sm",
                mode === item.value && "border-foreground/40 bg-secondary/40")}>
                <input type="radio" name="https-mode" className="mt-1" checked={mode === item.value}
                  onChange={() => setMode(item.value)} />
                <span>
                  <span className="font-medium">{t(item.label)}</span>
                  <span className="block text-xs text-muted-foreground">{t(item.hint)}</span>
                </span>
              </label>
            ))}
          </fieldset>
          {mode !== "off" && <HostsEditor hosts={hosts} onChange={setHosts} />}
          {leavesThisAddress && (
            <p className="flex gap-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
              <CircleAlert className="mt-0.5 size-4 shrink-0" />{t("https.notListed", { host: current })}
            </p>
          )}
          {mode !== "off" && <p className="text-xs text-muted-foreground">{t("https.portHint", { port: data.port })}</p>}
          <ErrorText error={save.error} />
          {moving && (
            <p className="flex items-center gap-2 rounded-lg border bg-secondary/40 px-3 py-2 text-sm">
              <Loader2 className="size-4 shrink-0 animate-spin" />
              <span>{t("https.moving", { seconds: MOVE_SECONDS })} <a className="underline" href={moving}>{moving}</a></span>
            </p>
          )}
          <Button type="submit" disabled={!changed || save.isPending || moving != null || (mode !== "off" && hosts.length === 0)}>
            {save.isPending && <Loader2 className="animate-spin" />}{t("common.save")}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}

function AuthorityCard({ data }: { data: Https }) {
  const t = useT()
  if (!data.authority) {
    return (
      <Card>
        <CardHeader><CardTitle>{t("https.authority")}</CardTitle></CardHeader>
        <CardContent className="text-sm text-muted-foreground">{t("https.authorityPending")}</CardContent>
      </Card>
    )
  }
  const { authority } = data
  return (
    <Card>
      <CardHeader><CardTitle>{t("https.authority")}</CardTitle></CardHeader>
      <CardContent className="space-y-4 text-sm">
        <p>{t("https.authorityIntro")}</p>
        <a className={buttonVariants({ variant: "outline" })} href={HTTPS_AUTHORITY_URL} download>
          <Download />{t("https.downloadAuthority")}
        </a>
        <dl className="divide-y rounded-lg border text-xs">
          <div className="grid gap-1 px-3 py-2 sm:grid-cols-[9rem_1fr]"><dt className="text-muted-foreground">{t("https.name")}</dt><dd>{authority.name}</dd></div>
          <div className="grid gap-1 px-3 py-2 sm:grid-cols-[9rem_1fr]"><dt className="text-muted-foreground">{t("https.fingerprint")}</dt><dd className="break-all font-mono">{authority.fingerprint}</dd></div>
          <div className="grid gap-1 px-3 py-2 sm:grid-cols-[9rem_1fr]"><dt className="text-muted-foreground">{t("https.authorityExpires")}</dt><dd>{formatDate(authority.not_after)}</dd></div>
          {authority.leaf_not_after && (
            <div className="grid gap-1 px-3 py-2 sm:grid-cols-[9rem_1fr]"><dt className="text-muted-foreground">{t("https.leafExpires")}</dt><dd>{t("https.leafRenewed", { date: formatDate(authority.leaf_not_after) })}</dd></div>
          )}
        </dl>
        <details className="rounded-lg border px-3 py-2">
          <summary className="cursor-pointer font-medium">{t("https.installTitle")}</summary>
          <ul className="mt-2 list-disc space-y-1.5 pl-5 text-muted-foreground">
            <li>{t("https.installMac")}</li>
            <li>{t("https.installIos")}</li>
            <li>{t("https.installAndroid")}</li>
            <li>{t("https.installWindows")}</li>
            <li>{t("https.installFirefox")}</li>
          </ul>
        </details>
      </CardContent>
    </Card>
  )
}

function CertificatesCard({ data }: { data: Https }) {
  const t = useT()
  const upload = useUploadCertificate()
  const remove = useDeleteCertificate()
  const [certificate, setCertificate] = useState<File | null>(null)
  const [key, setKey] = useState<File | null>(null)
  const [formKey, setFormKey] = useState(0)
  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    if (!certificate || !key) return
    upload.mutate({ certificate, key }, {
      onSuccess: () => {
        setCertificate(null)
        setKey(null)
        setFormKey((n) => n + 1)
      },
    })
  }
  return (
    <Card>
      <CardHeader><CardTitle>{t("https.certificates")}</CardTitle></CardHeader>
      <CardContent className="space-y-4 text-sm">
        <p className="text-muted-foreground">{t("https.certificatesIntro")}</p>
        {data.certificates.length > 0 && (
          <ul className="divide-y rounded-lg border">
            {data.certificates.map((cert, index) => (
              <li key={cert.fingerprint} className="flex items-start gap-3 px-3 py-2">
                <div className="min-w-0 flex-1 space-y-0.5">
                  <p className="break-all font-mono text-xs">{cert.names.join(", ")}</p>
                  <p className="text-xs text-muted-foreground">
                    {t("https.certIssuer", { issuer: cert.self_signed ? t("https.selfSigned") : cert.issuer })}
                    {" · "}
                    <span className={cn(new Date(cert.not_after).getTime() - Date.now() < 30 * 86_400_000 && "text-red-600 dark:text-red-400")}>
                      {t("https.certExpires", { date: formatDate(cert.not_after) })}
                    </span>
                  </p>
                  <p className="text-xs">
                    {cert.hosts.length ? t("https.certUsedFor", { hosts: cert.hosts.join(", ") }) : t("https.certUnused")}
                  </p>
                </div>
                <Button type="button" variant="ghost" size="sm" disabled={remove.isPending} aria-label={t("common.delete")}
                  onClick={() => confirm(t("https.confirmDeleteCert")) && remove.mutate(index)}>
                  <Trash2 />
                </Button>
              </li>
            ))}
          </ul>
        )}
        <ErrorText error={remove.error} />
        <form key={formKey} onSubmit={onSubmit} className="space-y-3 rounded-lg border border-dashed p-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <Label className="mb-1 block">{t("https.certFile")}</Label>
              <Input type="file" accept=".pem,.crt,.cer,.txt" className="pt-1.5 text-xs"
                onChange={(e) => setCertificate(e.target.files?.[0] ?? null)} />
            </div>
            <div>
              <Label className="mb-1 block">{t("https.keyFile")}</Label>
              <Input type="file" accept=".pem,.key,.txt" className="pt-1.5 text-xs"
                onChange={(e) => setKey(e.target.files?.[0] ?? null)} />
            </div>
          </div>
          <p className="text-xs text-muted-foreground">{t("https.uploadHint")}</p>
          <ErrorText error={upload.error} />
          <Button type="submit" variant="outline" disabled={!certificate || !key || upload.isPending}>
            {upload.isPending ? <Loader2 className="animate-spin" /> : <Upload />}{t("https.upload")}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}

/** HTTPS served by the app's web server: mode, hosts, certificates (admin only). */
export function HttpsTab() {
  const t = useT()
  const { data, error } = useHttps()
  // Mode chosen in the form, not saved yet: the certificates can be uploaded before switching to custom
  const [selected, setSelected] = useState<HttpsMode | null>(null)
  const [moving, setMoving] = useState<string | null>(null)
  if (error) return <ErrorText error={error} />
  if (!data) return <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
  return (
    <>
      {/* Remounted when the saved settings change, so the form starts from them */}
      <SettingsCard key={`${data.mode}|${data.hosts.join(",")}`} data={data} onMode={setSelected}
        moving={moving} onMoving={setMoving} />
      {data.mode === "internal" && <AuthorityCard data={data} />}
      {((selected ?? data.mode) === "custom" || data.certificates.length > 0) && <CertificatesCard data={data} />}
    </>
  )
}
