import { Suspense, useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AppShell } from './components/layout/AppShell'
import { ROUTES } from './lib/constants'
import { useAuthStore } from './stores/auth-store'
import {
  AnswerBank,
  Approvals,
  CaseThread,
  Cases,
  Command,
  Contacts,
  Dashboard,
  ExpertPage,
  NewExpert,
  Analytics,
  ApplicationDetail,
  Applications,
  Chat,
  Overview,
  JobFeed,
  Network,
  ApplyQueue,
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
        <Route path={ROUTES.LOGIN} element={<Login />} />

        {/* Authenticated/App Routes */}
        <Route element={<AppShell />}>
          <Route path={ROUTES.HOME} element={<Command />} />
          <Route path={ROUTES.CASES} element={<Cases />} />
          <Route path={ROUTES.CASE} element={<CaseThread />} />
          <Route path={ROUTES.APPROVALS} element={<Approvals />} />
          <Route path={ROUTES.CONTACTS} element={<Contacts />} />
          <Route path={ROUTES.ANSWERS} element={<AnswerBank />} />
          <Route path={ROUTES.DASHBOARD} element={<Dashboard />} />
          <Route path="/experts/new" element={<NewExpert />} />
          <Route path={ROUTES.EXPERT} element={<ExpertPage />} />
          <Route path={ROUTES.OVERVIEW} element={<Overview />} />
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
        <Route path="*" element={<Navigate to={ROUTES.HOME} replace />} />
      </Routes>
      </Suspense>
    </BrowserRouter>
  )
}

export default App
