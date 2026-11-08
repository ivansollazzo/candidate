import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { type ReactNode, StrictMode, useState } from "react"
import { createRoot } from "react-dom/client"
import { BrowserRouter, Navigate, Route, Routes } from "react-router"

import { Layout } from "@/app/Layout"
import { Overview } from "@/app/Overview"
import { SettingsPage } from "@/app/SettingsPage"
import { Agenda } from "@/features/applications/Agenda"
import { ApplicationDetail } from "@/features/applications/ApplicationDetail"
import { ApplicationList } from "@/features/applications/ApplicationList"
import { NewApplication } from "@/features/applications/NewApplication"
import { Login } from "@/features/auth/Login"
import { Welcome } from "@/features/auth/Welcome"
import { useAuthStatus, useCurrentUser, useMe } from "@/features/auth/hooks"
import { RestoreScreen } from "@/features/backups/RestoreScreen"
import { ProfilePage } from "@/features/profile/ProfilePage"
import { ThemeSync } from "@/features/users/theme"
import { ApiError } from "@/shared/lib/http"
import { I18nProvider } from "@/shared/lib/i18n"

import "./index.css"

// Session expired or closed elsewhere: back to the login screen
const onError = (error: Error) => {
  if (error instanceof ApiError && error.status === 401) queryClient.setQueryData(["me"], null)
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      // A refused request (4xx) is the answer; a server error is tried once more; a request that didn't reach the
      // server (the web server reloading after an HTTPS change, the backend restarting) a few times
      retry: (count, error) => (error instanceof ApiError ? error.status >= 500 && count < 1 : count < 3),
    },
  },
  queryCache: new QueryCache({ onError }),
  mutationCache: new MutationCache({ onError }),
})

/** The interface language follows the signed-in user. */
function UserLocale({ children }: { children: ReactNode }) {
  const { data: me, isPending } = useMe()
  return <I18nProvider userLocale={me?.language} loading={isPending}>{children}</I18nProvider>
}

/** First-run setup, login or the app, depending on session state. */
function AuthGate() {
  const me = useCurrentUser()
  const status = useAuthStatus()
  // Stays true for the whole first run, even after the admin is created
  const [setup, setSetup] = useState(false)
  if (status.data?.setup_required && !setup) setSetup(true)

  if (setup) {
    return <Welcome setup onSetupDone={() => {
      queryClient.setQueryData(["auth-status"], { ...status.data, setup_required: false })
      setSetup(false)
    }} />
  }
  if (!me) return status.isPending ? null : <Login />
  return (
    <Routes>
      <Route path="welcome" element={<Welcome />} />
      <Route element={<Layout />}>
        <Route index element={<Overview />} />
        <Route path="applications" element={<ApplicationList />} />
        <Route path="applications/new" element={<NewApplication />} />
        <Route path="applications/:id" element={<ApplicationDetail />} />
        <Route path="agenda" element={<Agenda />} />
        <Route path="profile" element={<ProfilePage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>
      {/* An unknown address (an old link, /login after signing in) shows the overview, not an empty page */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ThemeSync />
      <UserLocale>
        <BrowserRouter>
          <AuthGate />
        </BrowserRouter>
        <RestoreScreen />
      </UserLocale>
    </QueryClientProvider>
  </StrictMode>,
)
