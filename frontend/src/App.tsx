import { Suspense, useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AppShell } from './components/layout/AppShell'
import { ROUTES } from './lib/constants'
import { useAuthStore } from './stores/auth-store'
import {
  Analytics,
  ApplicationDetail,
  Applications,
  Chat,
  JobFeed,
  Network,
  ApplyQueue,
  Landing,
  Login,
  NewApplication,
  Profile,
  Settings,
  Templates,
} from './pages/lazy'


function App() {
  useEffect(() => {
    useAuthStore.getState().initialize()
  }, [])

  return (
    <BrowserRouter>
      <Suspense fallback={<div className="min-h-screen bg-background" />}>
      <Routes>
        {/* Public Routes */}
        <Route path="/" element={<Landing />} />
        <Route path={ROUTES.LOGIN} element={<Login />} />

        {/* Authenticated/App Routes */}
        <Route element={<AppShell />}>
          <Route path={ROUTES.CHAT} element={<Chat />} />
          <Route path={ROUTES.JOBS} element={<JobFeed />} />
          <Route path={ROUTES.NETWORK} element={<Network />} />
          <Route path={ROUTES.APPLY_QUEUE} element={<ApplyQueue />} />
          <Route path={ROUTES.APPLICATIONS} element={<Applications />} />
          <Route path={ROUTES.NEW_APPLICATION} element={<NewApplication />} />
          <Route path={ROUTES.APPLICATION_DETAIL} element={<ApplicationDetail />} />
          <Route path={ROUTES.PROFILE} element={<Profile />} />
          <Route path={ROUTES.TEMPLATES} element={<Templates />} />
          <Route path={ROUTES.ANALYTICS} element={<Analytics />} />
          <Route path={ROUTES.SETTINGS} element={<Settings />} />
        </Route>

        {/* Fallback Redirect */}
        <Route path="*" element={<Navigate to={ROUTES.CHAT} replace />} />
      </Routes>
      </Suspense>
    </BrowserRouter>
  )
}

export default App
