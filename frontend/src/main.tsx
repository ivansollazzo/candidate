import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { StrictMode, useState } from "react"
import { createRoot } from "react-dom/client"
import { BrowserRouter, Route, Routes } from "react-router"

import { Layout } from "@/components/Layout"
import { ApiError } from "@/lib/api"
import { useAuthStatus, useCurrentUser } from "@/lib/auth"
import { I18nProvider } from "@/lib/i18n"
import { ThemeSync } from "@/lib/theme"
import { Agenda } from "@/pages/Agenda"
import { ApplicationDetail } from "@/pages/ApplicationDetail"
import { ApplicationList } from "@/pages/ApplicationList"
import { Login } from "@/pages/Login"
import { NewApplication } from "@/pages/NewApplication"
import { Overview } from "@/pages/Overview"
import { ProfilePage } from "@/pages/Profile"
import { SettingsPage } from "@/pages/Settings"
import { Welcome } from "@/pages/Welcome"

import "./index.css"

// Session expired or closed elsewhere: back to the login screen
const onError = (error: Error) => {
  if (error instanceof ApiError && error.status === 401) queryClient.setQueryData(["me"], null)
}

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false, retry: 1 } },
  queryCache: new QueryCache({ onError }),
  mutationCache: new MutationCache({ onError }),
})

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
    </Routes>
  )
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ThemeSync />
      <I18nProvider>
        <BrowserRouter>
          <AuthGate />
        </BrowserRouter>
      </I18nProvider>
    </QueryClientProvider>
  </StrictMode>,
)
