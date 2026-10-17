import { useMutation, useQueryClient } from "@tanstack/react-query"
import { KeyRound, LogOut, RotateCcw } from "lucide-react"
import { type FormEvent, useState } from "react"
import { useNavigate } from "react-router"

import { isPasswordValid, NewPassword } from "@/components/PasswordInput"
import { RecoveryKey } from "@/components/RecoveryKey"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Field } from "@/components/ui/input"
import { api, type User } from "@/lib/api"
import { useLogout, useUpdateMe } from "@/lib/auth"
import { useT } from "@/lib/i18n"
import { useSettings } from "@/lib/settings"

const ErrorText = ({ error }: { error: Error | null }) =>
  error && <p className="text-sm text-red-600 dark:text-red-400">{error.message}</p>

function Details({ me }: { me: User }) {
  const t = useT()
  const update = useUpdateMe()
  const [username, setUsername] = useState(me.username)
  const [email, setEmail] = useState(me.email)
  const changed = username !== me.username || email !== me.email
  const submit = (e: FormEvent) => {
    e.preventDefault()
    update.mutate({ username, email })
  }
  return (
    <Card>
      <CardHeader><CardTitle>{t("account.details")}</CardTitle></CardHeader>
      <CardContent>
        <form onSubmit={submit} className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label={t("account.username")} autoComplete="username" required value={username}
              onChange={(e) => setUsername(e.target.value)} />
            <Field label={t("account.email")} type="email" autoComplete="email" required value={email}
              onChange={(e) => setEmail(e.target.value)} />
          </div>
          <p className="text-xs text-muted-foreground">{t("account.usernameHint")}</p>
          <ErrorText error={update.error} />
          <Button type="submit" disabled={!changed || update.isPending}>{t("common.save")}</Button>
        </form>
      </CardContent>
    </Card>
  )
}

function Password() {
  const t = useT()
  const queryClient = useQueryClient()
  const policy = useSettings()
  const [current, setCurrent] = useState("")
  const [password, setPassword] = useState("")
  const [confirm, setConfirm] = useState("")
  const change = useMutation({
    mutationFn: () => api.changePassword(current, password),
    onSuccess: (user) => {
      queryClient.setQueryData(["me"], user)
      setCurrent("")
      setPassword("")
      setConfirm("")
    },
  })
  const submit = (e: FormEvent) => {
    e.preventDefault()
    change.mutate()
  }
  return (
    <Card>
      <CardHeader><CardTitle>{t("account.password")}</CardTitle></CardHeader>
      <CardContent>
        <form onSubmit={submit} className="space-y-3">
          <Field label={t("password.current")} type="password" autoComplete="current-password" required value={current}
            className="sm:max-w-[calc(50%-0.375rem)]" onChange={(e) => setCurrent(e.target.value)} />
          <NewPassword value={password} confirm={confirm} onChange={setPassword} onConfirmChange={setConfirm} policy={policy} />
          <p className="text-xs text-muted-foreground">{t("account.passwordHint")}</p>
          <ErrorText error={change.error} />
          {change.isSuccess && <p className="text-sm text-emerald-700 dark:text-emerald-400">{t("account.passwordChanged")}</p>}
          <Button type="submit" disabled={!current || !isPasswordValid(password, confirm, policy) || change.isPending}>
            {t("account.passwordSubmit")}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}

function Recovery({ me }: { me: User }) {
  const t = useT()
  const [password, setPassword] = useState("")
  const generate = useMutation({ mutationFn: () => api.newRecoveryKey(password), onSuccess: () => setPassword("") })
  const submit = (e: FormEvent) => {
    e.preventDefault()
    generate.mutate()
  }
  return (
    <Card>
      <CardHeader><CardTitle>{t("recovery.title")}</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-muted-foreground">{t("account.recoveryText")}</p>
        {generate.data ? (
          <RecoveryKey username={me.username} value={generate.data.recovery_key} doneLabel={t("common.done")}
            onDone={() => generate.reset()} />
        ) : (
          <form onSubmit={submit} className="flex flex-wrap items-end gap-2">
            <Field label={t("password.current")} type="password" autoComplete="current-password" required
              value={password} onChange={(e) => setPassword(e.target.value)} />
            <Button type="submit" variant="outline" disabled={!password || generate.isPending}>
              <KeyRound />{t("account.recoveryGenerate")}
            </Button>
          </form>
        )}
        <ErrorText error={generate.error} />
      </CardContent>
    </Card>
  )
}

/** Current user's login details, photo, password and recovery key. */
export function AccountTab({ me }: { me: User }) {
  const t = useT()
  const navigate = useNavigate()
  const logout = useLogout()
  return (
    <>
      <Details key={me.updated_at} me={me} />
      <Password />
      <Recovery me={me} />
      <Card>
        <CardHeader><CardTitle>{t("settings.setup")}</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-muted-foreground">{t("settings.setupHint")}</p>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={() => navigate("/welcome")}><RotateCcw />{t("settings.setupButton")}</Button>
            <Button variant="outline" disabled={logout.isPending} onClick={() => logout.mutate()}>
              <LogOut />{t("nav.logout")}
            </Button>
          </div>
        </CardContent>
      </Card>
    </>
  )
}
