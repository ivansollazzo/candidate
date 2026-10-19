import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  ArrowLeft, ArrowRight, Check, FileUp, KeyRound, Languages, Plus, ShieldCheck, Sparkles, UserRound, UserRoundPlus,
} from "lucide-react"
import { type FormEvent, type ReactNode, useRef, useState } from "react"
import { useNavigate } from "react-router"

import { ErrorText } from "@/components/ErrorText"
import { Logo } from "@/components/Logo"
import { isPasswordValid, NewPassword } from "@/components/PasswordInput"
import { RecoveryKey } from "@/components/RecoveryKey"
import { Button } from "@/components/ui/button"
import { Field, Label, Textarea } from "@/components/ui/input"
import { api, type Profile } from "@/lib/api"
import { useAuthStatus, useCurrentUser, useUpdateMe } from "@/lib/auth"
import { getLocale, LOCALES, type Locale, type MessageKey, useSetGuestLocale, useT } from "@/lib/i18n"
import { useSettings, useUpdateSettings } from "@/lib/settings"
import { usePageTitle } from "@/lib/title"
import { cn } from "@/lib/utils"
import { AuthCard } from "@/pages/Login"

function Option({ selected, disabled, onClick, title, hint }: {
  selected: boolean
  disabled?: boolean
  onClick: () => void
  title: string
  hint?: string
}) {
  return (
    <button type="button" aria-pressed={selected} disabled={disabled} onClick={onClick}
      className={cn("flex w-full items-center gap-3 rounded-lg border p-4 text-left transition-colors hover:bg-secondary/50",
        selected && "border-foreground/40 bg-secondary")}>
      <span className="flex-1">
        <span className="block font-medium">{title}</span>
        {hint && <span className="block text-sm text-muted-foreground">{hint}</span>}
      </span>
      <span className={cn("flex size-5 items-center justify-center rounded-full border",
        selected && "border-foreground bg-foreground text-background")}>
        {selected && <Check className="size-3" />}
      </span>
    </button>
  )
}

function Step({ icon, title, text, children }: { icon: ReactNode; title: string; text?: string; children: ReactNode }) {
  usePageTitle(title)
  return (
    <div className="space-y-5">
      <div className="space-y-2">
        <span className="flex size-10 items-center justify-center rounded-full bg-secondary">{icon}</span>
        <h1 className="text-2xl font-semibold">{title}</h1>
        {text && <p className="text-muted-foreground">{text}</p>}
      </div>
      {children}
    </div>
  )
}

/** Admin account creation on first run. */
function AccountStep({ onCreated }: { onCreated: (username: string, key: string) => void }) {
  const t = useT()
  const queryClient = useQueryClient()
  const policy = useAuthStatus().data?.password_policy
  const [username, setUsername] = useState("")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [confirm, setConfirm] = useState("")
  const create = useMutation({
    mutationFn: () => api.setup({ username, email, password, language: getLocale() }),
    onSuccess: ({ user, recovery_key }) => {
      queryClient.setQueryData(["me"], user)
      onCreated(user.username, recovery_key)
    },
  })
  const submit = (e: FormEvent) => {
    e.preventDefault()
    create.mutate()
  }
  return (
    <form onSubmit={submit} className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={t("account.username")} autoComplete="username" autoFocus required value={username}
          onChange={(e) => setUsername(e.target.value)} />
        <Field label={t("account.email")} type="email" autoComplete="email" required value={email}
          onChange={(e) => setEmail(e.target.value)} />
      </div>
      <NewPassword value={password} confirm={confirm} onChange={setPassword} onConfirmChange={setConfirm}
        policy={policy} label={t("password.label")} />
      <ErrorText error={create.error} />
      <Button type="submit" disabled={create.isPending || !isPasswordValid(password, confirm, policy)}>
        <UserRoundPlus />{t("wizard.accountCreate")}
      </Button>
    </form>
  )
}

const PROFILE_FIELDS = ["full_name", "headline", "location", "years_of_experience", "summary"] as const
type ProfileFields = Pick<Profile, (typeof PROFILE_FIELDS)[number]>

/** Basic profile details and an optional CV. */
function ProfileStep({ profile, onNext }: { profile: Profile; onNext: () => void }) {
  const t = useT()
  const queryClient = useQueryClient()
  const input = useRef<HTMLInputElement>(null)
  const [fields, setFields] = useState(
    () => Object.fromEntries(PROFILE_FIELDS.map((k) => [k, profile[k]])) as ProfileFields)
  const set = (changes: Partial<ProfileFields>) => setFields({ ...fields, ...changes })
  const save = useMutation({
    mutationFn: () => api.updateProfile(fields),
    onSuccess: (data) => {
      queryClient.setQueryData(["profile"], data)
      onNext()
    },
  })
  const upload = useMutation({ mutationFn: api.uploadCv, onSuccess: (data) => queryClient.setQueryData(["profile"], data) })
  const cvName = upload.data?.cv_filename ?? profile.cv_filename
  const submit = (e: FormEvent) => {
    e.preventDefault()
    save.mutate()
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={t("profile.fullName")} autoComplete="name" value={fields.full_name ?? ""}
          onChange={(e) => set({ full_name: e.target.value || null })} />
        <Field label={t("profile.headline")} value={fields.headline ?? ""}
          onChange={(e) => set({ headline: e.target.value || null })} />
        <Field label={t("profile.city")} value={fields.location ?? ""}
          onChange={(e) => set({ location: e.target.value || null })} />
        <Field label={t("profile.years")} type="number" min={0} max={60} step={0.5}
          value={fields.years_of_experience ?? ""}
          onChange={(e) => set({ years_of_experience: Number.isNaN(e.target.valueAsNumber) ? null : e.target.valueAsNumber })} />
      </div>
      <div>
        <Label htmlFor="wizard-summary" className="mb-1 block">{t("profile.summary")}</Label>
        <Textarea id="wizard-summary" value={fields.summary ?? ""} onChange={(e) => set({ summary: e.target.value || null })} />
      </div>
      <div className="flex flex-wrap items-center gap-3 rounded-lg border border-dashed p-3 text-sm">
        <input ref={input} type="file" className="hidden" accept=".pdf,.docx,.txt,.md"
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) upload.mutate(file)
            e.target.value = ""
          }} />
        <Button type="button" variant="outline" size="sm" disabled={upload.isPending} onClick={() => input.current?.click()}>
          <FileUp />{t(cvName ? "profile.uploadNew" : "profile.upload")}
        </Button>
        <span className="min-w-0 flex-1 text-muted-foreground">
          {cvName ? <span className="flex items-center gap-1.5"><Check className="size-4 text-emerald-600" />{cvName}</span>
            : t("wizard.profileCvHint")}
        </span>
      </div>
      <ErrorText error={save.error ?? upload.error} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={save.isPending}>{t("wizard.profileSave")}<ArrowRight /></Button>
        <Button type="button" variant="ghost" onClick={onNext}>{t("wizard.skip")}</Button>
      </div>
    </form>
  )
}

type StepId = "language" | "account" | "key" | "ai" | "disclaimer" | "profile" | "first"
// Steps advanced by the bottom button; the others have their own buttons
const FREE_STEPS: StepId[] = ["language", "ai", "disclaimer"]

/**
 * Initial setup. With `setup` it is the app's first run and also creates the admin;
 * otherwise every user sees it on first login, and it can be rerun from settings.
 */
export function Welcome({ setup, onSetupDone }: { setup?: boolean; onSetupDone?: () => void }) {
  const t = useT()
  const navigate = useNavigate()
  const me = useCurrentUser()
  const settings = useSettings()
  const updateSettings = useUpdateSettings()
  const updateMe = useUpdateMe()
  const setGuestLocale = useSetGuestLocale()
  const { data: profile } = useQuery({ queryKey: ["profile"], queryFn: api.getProfile, enabled: me != null })
  const [index, setIndex] = useState(0)
  const [key, setKey] = useState<{ username: string; value: string } | null>(null)

  const steps: StepId[] = setup
    ? ["language", "account", "key", "ai", "disclaimer", "profile", "first"]
    : ["language", ...(me?.role === "admin" ? ["ai" as const] : []), "disclaimer", "profile", "first"]
  const step = steps[index]
  const next = () => setIndex(index + 1)
  // Once the account exists, there is no going back to its creation step
  const firstBack = key ? steps.indexOf("key") + 1 : 1
  const pending = updateMe.isPending || updateSettings.isPending

  const chooseLanguage = (language: Locale) => (me ? updateMe.mutate({ language }) : setGuestLocale(language))
  const finish = (to: string) => updateMe.mutate({ onboarded: true }, {
    onSuccess: () => {
      onSetupDone?.()
      navigate(to)
    },
  })
  const disclaimers: MessageKey[] = [
    "wizard.disclaimerLocal",
    ...(settings?.llm_enabled ? ["wizard.disclaimerAi" as const] : []),
    "wizard.disclaimerMatch",
    "wizard.disclaimerData",
  ]

  return (
    <AuthCard>
      <div className="flex items-center gap-3">
        <Logo />
        <div className="flex flex-1 gap-1">
          {steps.map((id, i) => (
            <span key={id} className={cn("h-1 flex-1 rounded-full", i <= index ? "bg-foreground" : "bg-secondary")} />
          ))}
        </div>
        <span className="text-xs text-muted-foreground">{t("wizard.step", { step: index + 1, total: steps.length })}</span>
      </div>

      {step === "language" && (
        <Step icon={<Languages className="size-5" />} title={t("wizard.welcome")} text={t("wizard.languageText")}>
          <div className="space-y-2">
            {LOCALES.map((l) => (
              <Option key={l.value} title={l.label} selected={getLocale() === l.value} disabled={pending}
                onClick={() => chooseLanguage(l.value)} />
            ))}
          </div>
        </Step>
      )}

      {step === "account" && (
        <Step icon={<UserRound className="size-5" />} title={t("wizard.accountTitle")} text={t("wizard.accountText")}>
          <AccountStep onCreated={(username, value) => {
            setKey({ username, value })
            next()
          }} />
        </Step>
      )}

      {step === "key" && key && (
        <Step icon={<KeyRound className="size-5" />} title={t("wizard.keyTitle")} text={t("wizard.keyText")}>
          <RecoveryKey username={key.username} value={key.value} doneLabel={t("wizard.next")} onDone={next} />
        </Step>
      )}

      {step === "ai" && (
        <Step icon={<Sparkles className="size-5" />} title={t("wizard.aiTitle")} text={t("wizard.aiText")}>
          <div className="space-y-2">
            <Option title={t("wizard.aiOn")} hint={t("wizard.aiOnHint")} selected={settings?.llm_enabled === true}
              disabled={pending} onClick={() => updateSettings.mutate({ llm_enabled: true })} />
            <Option title={t("wizard.aiOff")} hint={t("wizard.aiOffHint")} selected={settings?.llm_enabled === false}
              disabled={pending} onClick={() => updateSettings.mutate({ llm_enabled: false })} />
          </div>
        </Step>
      )}

      {step === "disclaimer" && (
        <Step icon={<ShieldCheck className="size-5" />} title={t("wizard.disclaimerTitle")}>
          <ul className="space-y-3 text-sm">
            {disclaimers.map((item) => (
              <li key={item} className="flex gap-2.5">
                <Check className="mt-0.5 size-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
                <span>{t(item)}</span>
              </li>
            ))}
          </ul>
        </Step>
      )}

      {step === "profile" && (
        <Step icon={<UserRound className="size-5" />} title={t("wizard.profileTitle")} text={t("wizard.profileText")}>
          {profile ? <ProfileStep profile={profile} onNext={next} />
            : <p className="text-sm text-muted-foreground">{t("common.loading")}</p>}
        </Step>
      )}

      {step === "first" && (
        <Step icon={<Plus className="size-5" />} title={t("wizard.firstTitle")} text={t("wizard.firstText")}>
          <div className="flex flex-wrap gap-2">
            <Button disabled={pending} onClick={() => finish("/applications/new")}><Plus />{t("wizard.firstAdd")}</Button>
            <Button variant="ghost" disabled={pending} onClick={() => finish("/")}>{t("wizard.skip")}</Button>
          </div>
        </Step>
      )}

      <ErrorText error={updateMe.error ?? updateSettings.error} />

      <div className="flex justify-between border-t pt-4">
        {index >= firstBack ? (
          <Button variant="ghost" onClick={() => setIndex(index - 1)}><ArrowLeft />{t("wizard.back")}</Button>
        ) : <span />}
        {FREE_STEPS.includes(step) && (
          <Button onClick={next} disabled={step === "ai" && !settings}>{t("wizard.next")}<ArrowRight /></Button>
        )}
      </div>
    </AuthCard>
  )
}
