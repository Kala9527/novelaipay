import { useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { Activity, ArrowRightFromLine, BookOpen, CreditCard, Images, KeyRound, LayoutDashboard, PanelLeftClose, PanelLeftOpen, Settings2, Store, UserRound, WandSparkles } from 'lucide-react'
import type { User } from '../types'
import { api, formatMoney } from '../lib/api'
import { PublicHeader } from './PublicHeader'

export function Layout({ user, onLogout }: { user: User; onLogout: () => void }) {
  const navigate = useNavigate()
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem('novelaipay-sidebar-collapsed') === '1')
  function toggleSidebar() {
    setCollapsed(value => {
      localStorage.setItem('novelaipay-sidebar-collapsed', value ? '0' : '1')
      return !value
    })
  }
  async function signOut() {
    try {
      await api('/api/auth/logout', { method: 'POST' })
      onLogout()
      navigate('/login', { replace: true })
    } catch (error) { window.alert(`退出失败：${(error as Error).message}`) }
  }
  const links = [
    { to: '/', label: '概览', icon: LayoutDashboard },
    { to: '/models', label: '模型广场', icon: Store },
    { to: '/keys', label: 'API 密钥', icon: KeyRound },
    { to: '/workshop', label: '生图工作台', icon: WandSparkles },
    { to: '/jobs', label: '使用记录', icon: Images },
    { to: '/billing', label: '账单流水', icon: CreditCard },
    { to: '/api-guide', label: '接口文档', icon: BookOpen },
    { to: '/profile', label: '用户管理', icon: UserRound },
    ...(user.is_admin ? [{ to: '/admin', label: '管理设置', icon: Settings2 }] : []),
  ]
  return <div className={`app-shell ${collapsed ? 'sidebar-collapsed' : ''}`}>
    <PublicHeader loggedIn />
    <aside className="sidebar">
      <div className="sidebar-head"><div className="brand"><span className="brand-mark"><Activity size={19} strokeWidth={2.4} /></span><div className="sidebar-text"><strong>Novelaipay</strong><small>IMAGE API CONSOLE</small></div></div><button type="button" className="sidebar-toggle icon-button" aria-label={collapsed ? '展开侧栏' : '收起侧栏'} title={collapsed ? '展开侧栏' : '收起侧栏'} onClick={toggleSidebar}>{collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}</button></div>
      <nav className="side-nav">{links.map(({ to, label, icon: Icon }) => <NavLink key={to} end={to === '/'} to={to} title={collapsed ? label : undefined} className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}><Icon size={18} /><span className="nav-label">{label}</span></NavLink>)}</nav>
      <div className="sidebar-bottom"><div className="sidebar-text"><div className="sidebar-label">账户余额</div><div className="sidebar-balance">{formatMoney(user.balance)}</div></div><button className="account-button" onClick={signOut} title="退出登录"><span className="sidebar-text">{user.name || user.email}</span><ArrowRightFromLine size={17} /></button></div>
    </aside>
    <main className="main-area"><Outlet /></main>
  </div>
}
