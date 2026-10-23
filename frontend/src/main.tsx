import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClientProvider } from '@tanstack/react-query'
import { queryClient } from './lib/query-client'
import App from './App.tsx'
import './index.css'
import { applyTheme, getThemePreference } from './lib/theme'
import { useAuthStore } from './stores/auth-store'

// Apply the saved theme before first paint.
applyTheme(getThemePreference())

function AccountProvider() {
  const accountId = useAuthStore((state) => state.user?.id ?? 'signed-out');
  return <QueryClientProvider key={accountId} client={queryClient}><App /></QueryClientProvider>;
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode><AccountProvider /></React.StrictMode>,
)
