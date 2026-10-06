import { useCallback, useEffect, useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { api } from './lib/api'
import type { User } from './types'
import { Layout } from './components/Layout'
import { LoginPage } from './pages/LoginPage'
import { DashboardPage } from './pages/DashboardPage'
import { KeysPage } from './pages/KeysPage'
import { JobsPage } from './pages/JobsPage'
import { UsagePage } from './pages/UsagePage'
import { BillingRecordsPage } from './pages/BillingRecordsPage'
import { AdminPage } from './pages/AdminPage'
import { ApiGuidePage } from './pages/ApiGuidePage'
import { ModelPlazaPage } from './pages/ModelPlazaPage'
import { ProfilePage } from './pages/ProfilePage'
import { PublicHeader } from './components/PublicHeader'
import { RedemptionPage } from './pages/RedemptionPage'
import { Outlet } from 'react-router-dom'

function PublicLayout() { return <><PublicHeader loggedIn={false} /><Outlet /></> }

export function App() {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const refresh = useCallback(async () => {
    try { setUser(await api<User>('/api/auth/me')) }
    catch { setUser(null) }
    finally { setLoading(false) }
  }, [])
  const signedOut = useCallback(() => setUser(null), [])
  useEffect(() => {
    refresh()
    const interval = window.setInterval(refresh, 5000)
    const onVisible = () => { if (document.visibilityState === 'visible') refresh() }
    document.addEventListener('visibilitychange', onVisible)
    window.addEventListener('focus', refresh)
    window.addEventListener('novelaipay:data-changed', refresh)
    return () => {
      window.clearInterval(interval)
      document.removeEventListener('visibilitychange', onVisible)
      window.removeEventListener('focus', refresh)
      window.removeEventListener('novelaipay:data-changed', refresh)
    }
  }, [refresh])
  if (loading) return <div className="loading">正在加载 Novelaipay...</div>
  return <Routes>
    <Route path="/login" element={user ? <Navigate to="/" /> : <LoginPage onLogin={refresh} />} />
    <Route element={user ? <Layout user={user} onLogout={signedOut} /> : <PublicLayout />}>
      <Route path="/models" element={<ModelPlazaPage />} />
    </Route>
    <Route element={user ? <Layout user={user} onLogout={signedOut} /> : <Navigate to="/login" />}>
      <Route path="/" element={<DashboardPage user={user!} />} />
      <Route path="/keys" element={<KeysPage />} />
      <Route path="/workshop" element={<JobsPage userId={user?.id ?? 0} />} />
      <Route path="/jobs" element={<UsagePage isAdmin={user?.is_admin ?? false} />} />
      <Route path="/billing" element={<BillingRecordsPage isAdmin={user?.is_admin ?? false} />} />
      <Route path="/redemption" element={<RedemptionPage />} />
      <Route path="/profile" element={<ProfilePage user={user!} onUpdated={refresh} />} />
      <Route path="/api-guide" element={<ApiGuidePage />} />
      <Route path="/admin" element={user?.is_admin ? <AdminPage /> : <Navigate to="/" />} />
    </Route>
    <Route path="*" element={<Navigate to="/" />} />
  </Routes>
}
