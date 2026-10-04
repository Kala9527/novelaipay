import { useCallback, useEffect, useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { api } from './lib/api'
import type { User } from './types'
import { Layout } from './components/Layout'
import { LoginPage } from './pages/LoginPage'
import { DashboardPage } from './pages/DashboardPage'
import { KeysPage } from './pages/KeysPage'
import { JobsPage } from './pages/JobsPage'
import { BillingPage } from './pages/BillingPage'
import { AdminPage } from './pages/AdminPage'

export function App() {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const refresh = useCallback(() => { api<User>('/api/auth/me').then(setUser).catch(() => setUser(null)).finally(() => setLoading(false)) }, [])
  useEffect(() => { refresh() }, [refresh])
  if (loading) return <div className="loading">正在加载 Novelaipay...</div>
  return <Routes>
    <Route path="/login" element={user ? <Navigate to="/" /> : <LoginPage onLogin={refresh} />} />
    <Route element={user ? <Layout user={user} refresh={refresh} /> : <Navigate to="/login" />}>
      <Route path="/" element={<DashboardPage user={user!} />} />
      <Route path="/keys" element={<KeysPage />} />
      <Route path="/jobs" element={<JobsPage />} />
      <Route path="/billing" element={<BillingPage />} />
      <Route path="/admin" element={user?.is_admin ? <AdminPage /> : <Navigate to="/" />} />
    </Route>
    <Route path="*" element={<Navigate to="/" />} />
  </Routes>
}
