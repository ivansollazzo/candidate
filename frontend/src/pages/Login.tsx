import { useMutation } from "@tanstack/react-query"
import { ArrowLeft, LogIn } from "lucide-react"
import { type FormEvent, type ReactNode, useState } from "react"

import { ErrorText } from "@/components/ErrorText"
import { LanguageSelect } from "@/components/LanguageSelect"
import { Logo } from "@/components/Logo"
import { isPasswordValid, NewPassword } from "@/components/PasswordInput"
import { RecoveryKey } from "@/components/RecoveryKey"
import { Button } from "@/components/ui/button"
import { Field } from "@/components/ui/input"
import { api, type UserWithKey } from "@/lib/api"
import { useAuthStatus, useSignIn } from "@/lib/auth"
import { getLocale, useSetGuestLocale, useT } from "@/lib/i18n"
import { usePageTitle } from "@/lib/title"

/** Centered card for logged-out screens (login and first run). */
export function AuthCard({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <div className="w-full max-w-lg space-y-6 rounded-2xl border bg-card p-6 shadow-sm sm:p-8">{children}</div>
    </div>
  )
}

function SignInForm({ onForgot }: { onForgot: () => void }) {
  const t = useT()
  usePageTitle(t("login.title"))
  const signIn = useSignIn()
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const login = useMutation({ mutationFn: () => api.login(username, password), onSuccess: signIn })
  const submit = (e: FormEvent) => {
    e.preventDefault()
    login.mutate()
  }
  return (
    <form onSubmit={submit} className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">{t("login.title")}</h1>
        <p className="text-sm text-muted-foreground">{t("login.text")}</p>
      </div>
      <Field label={t("account.username")} autoComplete="username" autoFocus required value={username}
        onChange={(e) => setUsername(e.target.value)} />
      <Field label={t("password.label")} type="password" autoComplete="current-password" required value={password}
        onChange={(e) => setPassword(e.target.value)} />
      <ErrorText error={login.error} />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Button type="submit" disabled={login.isPending}><LogIn />{t("login.submit")}</Button>
        <button type="button" onClick={onForgot} className="text-sm text-muted-foreground underline hover:text-foreground">
          {t("login.forgot")}
        </button>
      </div>
      <p className="text-xs text-muted-foreground">{t("login.noAccount")}</p>
    </form>
  )
}

function ResetForm({ onBack }: { onBack: () => void }) {
  const t = useT()
  usePageTitle(t("reset.title"))
  const signIn = useSignIn()
  const policy = useAuthStatus().data?.password_policy
  const [username, setUsername] = useState("")
  const [key, setKey] = useState("")
  const [password, setPassword] = useState("")
  const [confirm, setConfirm] = useState("")
  // The user is let in only after saving the new key
  const [result, setResult] = useState<UserWithKey | null>(null)
  const reset = useMutation({ mutationFn: () => api.resetPassword(username, key, password), onSuccess: setResult })

  if (result) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-semibold">{t("reset.done")}</h1>
        <p className="text-sm text-muted-foreground">{t("reset.doneText")}</p>
        <RecoveryKey username={result.user.username} value={result.recovery_key} doneLabel={t("reset.enter")}
          onDone={() => signIn(result.user)} />
      </div>
    )
  }

  const submit = (e: FormEvent) => {
    e.preventDefault()
    reset.mutate()
  }
  return (
    <form onSubmit={submit} className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">{t("reset.title")}</h1>
        <p className="text-sm text-muted-foreground">{t("reset.text")}</p>
      </div>
      <Field label={t("account.username")} autoComplete="username" required value={username}
        onChange={(e) => setUsername(e.target.value)} />
      <Field label={t("reset.key")} placeholder="ABCD-EFGH-…" required value={key} className="font-mono"
        onChange={(e) => setKey(e.target.value)} />
      <NewPassword value={password} confirm={confirm} onChange={setPassword} onConfirmChange={setConfirm} policy={policy} />
      <ErrorText error={reset.error} />
      <div className="flex flex-wrap justify-between gap-2">
        <Button type="button" variant="ghost" onClick={onBack}><ArrowLeft />{t("reset.back")}</Button>
        <Button type="submit" disabled={reset.isPending || !isPasswordValid(password, confirm, policy)}>
          {t("reset.submit")}
        </Button>
      </div>
    </form>
  )
}

export function Login() {
  const [forgot, setForgot] = useState(false)
  const setLocale = useSetGuestLocale()
  return (
    <AuthCard>
      <div className="flex items-center justify-between">
        <Logo />
        <LanguageSelect className="w-32" value={getLocale()} onChange={setLocale} />
      </div>
      {forgot ? <ResetForm onBack={() => setForgot(false)} /> : <SignInForm onForgot={() => setForgot(true)} />}
    </AuthCard>
  )
}
