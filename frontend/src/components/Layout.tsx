import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { Activity, ArrowRightFromLine, CreditCard, Images, KeyRound, LayoutDashboard, Settings2, WandSparkles } from 'lucide-react'
import type { User } from '../types'
import { api, formatMoney } from '../lib/api'

export function Layout({ user, onLogout }: { user: User; onLogout: () => void }) {
  const navigate = useNavigate()
  async function signOut() {
    try {
      await api('/api/auth/logout', { method: 'POST' })
      onLogout()
      navigate('/login', { replace: true })
    } catch (error) { window.alert(`退出失败：${(error as Error).message}`) }
  }
  const links = [
    { to: '/', label: '概览', icon: LayoutDashboard },
    { to: '/keys', label: 'API 密钥', icon: KeyRound },
    { to: '/workshop', label: '生图工作台', icon: WandSparkles },
    { to: '/jobs', label: '使用记录', icon: Images },
    { to: '/billing', label: '账单流水', icon: CreditCard },
    ...(user.is_admin ? [{ to: '/admin', label: '管理设置', icon: Settings2 }] : []),
  ]
  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark"><Activity size={19} strokeWidth={2.4} /></span><div><strong>Novelaipay</strong><small>IMAGE API CONSOLE</small></div></div>
      <nav className="side-nav">{links.map(({ to, label, icon: Icon }) => <NavLink key={to} end={to === '/'} to={to} className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}><Icon size={18} />{label}</NavLink>)}</nav>
      <div className="sidebar-bottom"><div className="sidebar-label">账户余额</div><div className="sidebar-balance">{formatMoney(user.balance)}</div><button className="account-button" onClick={signOut} title="退出登录"><span>{user.name || user.email}</span><ArrowRightFromLine size={17} /></button></div>
    </aside>
    <main className="main-area"><header className="mobile-header"><span className="brand-mini">Novelaipay</span><div className="mobile-account"><span>{formatMoney(user.balance)}</span><button type="button" className="icon-button" title="退出登录" onClick={signOut}><ArrowRightFromLine size={17} /></button></div></header><Outlet /></main>
  </div>
}
