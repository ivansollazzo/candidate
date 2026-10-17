import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Pencil, Plus, Trash2, X } from "lucide-react"
import { type FormEvent, useState } from "react"

import { Avatar } from "@/components/Avatar"
import { LanguageSelect } from "@/components/LanguageSelect"
import { isPasswordValid, NewPassword } from "@/components/PasswordInput"
import { RecoveryKey } from "@/components/RecoveryKey"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Field, Label, Select } from "@/components/ui/input"
import { api, type Role, type User, type UserWithKey } from "@/lib/api"
import { type Locale, useT } from "@/lib/i18n"
import { useSettings } from "@/lib/settings"
import { cn } from "@/lib/utils"

function RoleSelect({ value, onChange }: { value: Role; onChange: (role: Role) => void }) {
  const t = useT()
  return (
    <div>
      <Label className="mb-1 block">{t("users.role")}</Label>
      <Select value={value} onChange={(e) => onChange(e.target.value as Role)}>
        <option value="user">{t("role.user")}</option>
        <option value="admin">{t("role.admin")}</option>
      </Select>
    </div>
  )
}

/** Creates a user or edits the given one; password is required only for new users. */
function UserForm({ user, onSaved, onCancel }: {
  user?: User
  onSaved: (result: User | UserWithKey) => void
  onCancel: () => void
}) {
  const t = useT()
  const policy = useSettings()
  const [username, setUsername] = useState(user?.username ?? "")
  const [email, setEmail] = useState(user?.email ?? "")
  const [role, setRole] = useState<Role>(user?.role ?? "user")
  const [language, setLanguage] = useState<Locale>("it")
  const [password, setPassword] = useState("")
  const [confirm, setConfirm] = useState("")
  const save = useMutation({
    mutationFn: () => user
      ? api.updateUser(user.id, { username, email, role, ...(password ? { password } : {}) })
      : api.createUser({ username, email, role, language, password }),
    onSuccess: onSaved,
  })
  const passwordOk = (user && !password && !confirm) || isPasswordValid(password, confirm, policy)
  const submit = (e: FormEvent) => {
    e.preventDefault()
    save.mutate()
  }

  return (
    <form onSubmit={submit} className="space-y-3 rounded-lg border bg-secondary/30 p-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={t("account.username")} required value={username} onChange={(e) => setUsername(e.target.value)} />
        <Field label={t("account.email")} type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        <RoleSelect value={role} onChange={setRole} />
        {!user && (
          <div>
            <Label className="mb-1 block">{t("settings.language")}</Label>
            <LanguageSelect value={language} onChange={setLanguage} />
          </div>
        )}
      </div>
      <NewPassword value={password} confirm={confirm} onChange={setPassword} onConfirmChange={setConfirm} policy={policy}
        label={t(user ? "users.newPassword" : "password.label")} />
      {user && <p className="text-xs text-muted-foreground">{t("users.passwordHint")}</p>}
      {save.error && <p className="text-sm text-red-600 dark:text-red-400">{save.error.message}</p>}
      <div className="flex gap-2">
        <Button type="submit" disabled={!passwordOk || save.isPending}>{t(user ? "common.save" : "users.create")}</Button>
        <Button type="button" variant="ghost" onClick={onCancel}>{t("common.cancel")}</Button>
      </div>
    </form>
  )
}

/** User list: only the admin can create, edit and delete users. */
export function UsersTab({ me }: { me: User }) {
  const t = useT()
  const queryClient = useQueryClient()
  const { data: users = [], error } = useQuery({ queryKey: ["users"], queryFn: api.listUsers })
  // "new" = create form open; a number = id of the user being edited
  const [editing, setEditing] = useState<"new" | number | null>(null)
  const [created, setCreated] = useState<UserWithKey | null>(null)
  const remove = useMutation({
    mutationFn: api.deleteUser,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["users"] }),
  })

  const saved = (result: User | UserWithKey) => {
    queryClient.invalidateQueries({ queryKey: ["users"] })
    if ("recovery_key" in result) setCreated(result)
    else if (result.id === me.id) queryClient.setQueryData(["me"], result)
    setEditing(null)
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("users.title")}</CardTitle>
        {editing !== "new" && !created && (
          <Button size="sm" onClick={() => setEditing("new")}><Plus />{t("users.add")}</Button>
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">{t("users.intro")}</p>
        {created && (
          <div className="space-y-2">
            <p className="text-sm font-medium">{t("users.created", { username: created.user.username })}</p>
            <RecoveryKey forOther username={created.user.username} value={created.recovery_key}
              doneLabel={t("common.done")} onDone={() => setCreated(null)} />
          </div>
        )}
        {editing === "new" && <UserForm onSaved={saved} onCancel={() => setEditing(null)} />}
        {(error || remove.error) && (
          <p className="text-sm text-red-600 dark:text-red-400">{(error ?? remove.error)?.message}</p>
        )}
        <ul className="divide-y rounded-lg border">
          {users.map((user) => (
            <li key={user.id} className="space-y-3 px-3 py-2.5">
              <div className="flex items-center gap-3">
                <Avatar user={user} className="size-8" />
                <div className="min-w-0 flex-1 text-sm">
                  <p className="truncate font-medium">
                    {user.username}
                    {user.id === me.id && <span className="font-normal text-muted-foreground"> · {t("users.you")}</span>}
                  </p>
                  <p className="truncate text-muted-foreground">{user.email}</p>
                </div>
                <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium",
                  user.role === "admin"
                    ? "bg-violet-100 text-violet-800 dark:bg-violet-900 dark:text-violet-200"
                    : "bg-secondary text-muted-foreground")}>
                  {t(`role.${user.role}`)}
                </span>
                <Button size="icon" variant="ghost" aria-label={t("common.edit")} title={t("common.edit")}
                  onClick={() => setEditing(editing === user.id ? null : user.id)}>
                  {editing === user.id ? <X /> : <Pencil />}
                </Button>
                <Button size="icon" variant="ghost" aria-label={t("common.delete")} title={t("common.delete")}
                  disabled={user.id === me.id || remove.isPending}
                  onClick={() => confirm(t("users.confirmDelete", { username: user.username })) && remove.mutate(user.id)}>
                  <Trash2 />
                </Button>
              </div>
              {editing === user.id && <UserForm user={user} onSaved={saved} onCancel={() => setEditing(null)} />}
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  )
}
