import { useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AppShell } from './components/layout/AppShell'
import Dashboard from './pages/Dashboard'
import Applications from './pages/Applications'
import NewApplication from './pages/NewApplication'
import ApplicationDetail from './pages/ApplicationDetail'
import Profile from './pages/Profile'
import Templates from './pages/Templates'
import Analytics from './pages/Analytics'
import Settings from './pages/Settings'
import Login from './pages/Login'
import { ROUTES } from './lib/constants'
import { useAuthStore } from './stores/auth-store'

function App() {
  useEffect(() => {
    useAuthStore.getState().initialize()
  }, [])

  return (
    <BrowserRouter>
      <Routes>
        {/* Public Routes */}
        <Route path={ROUTES.LOGIN} element={<Login />} />

        {/* Authenticated/App Routes */}
        <Route element={<AppShell />}>
          <Route path="/" element={<Navigate to={ROUTES.DASHBOARD} replace />} />
          <Route path={ROUTES.DASHBOARD} element={<Dashboard />} />
          <Route path={ROUTES.APPLICATIONS} element={<Applications />} />
          <Route path={ROUTES.NEW_APPLICATION} element={<NewApplication />} />
          <Route path={ROUTES.APPLICATION_DETAIL} element={<ApplicationDetail />} />
          <Route path={ROUTES.PROFILE} element={<Profile />} />
          <Route path={ROUTES.TEMPLATES} element={<Templates />} />
          <Route path={ROUTES.ANALYTICS} element={<Analytics />} />
          <Route path={ROUTES.SETTINGS} element={<Settings />} />
        </Route>

        {/* Fallback Redirect */}
        <Route path="*" element={<Navigate to={ROUTES.DASHBOARD} replace />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
