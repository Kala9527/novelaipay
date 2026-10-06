import { useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { ArrowRightFromLine, BookOpen, CreditCard, Gift, Images, KeyRound, LayoutDashboard, PanelLeftClose, PanelLeftOpen, Settings2, Store, UserRound, WandSparkles, Rocket, SlidersHorizontal } from 'lucide-react'
import type { User } from '../types'
import { api, formatMoney } from '../lib/api'
import { PublicHeader } from './PublicHeader'
import brandIcon from '../assets/brand-icon.svg'
import { usePreferences } from '../lib/preferences'

export function Layout({ user, onLogout }: { user: User; onLogout: () => void }) {
  const { t } = usePreferences()
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
    { to: '/', label: t('overview'), icon: LayoutDashboard },
    { to: '/quickstart', label: t('quickstart'), icon: Rocket },
    { to: '/models', label: t('models'), icon: Store },
    { to: '/keys', label: t('keys'), icon: KeyRound },
    { to: '/workshop', label: t('workshop'), icon: WandSparkles },
    { to: '/jobs', label: t('usage'), icon: Images },
    { to: '/billing', label: t('billing'), icon: CreditCard },
    { to: '/redemption', label: t('redemption'), icon: Gift },
    { to: '/api-guide', label: t('guide'), icon: BookOpen },
    { to: '/profile', label: t('profile'), icon: UserRound },
    { to: '/preferences', label: t('preferences'), icon: SlidersHorizontal },
    ...(user.is_admin ? [{ to: '/admin', label: t('admin'), icon: Settings2 }] : []),
  ]
  return <div className={`app-shell ${collapsed ? 'sidebar-collapsed' : ''}`}>
    <PublicHeader loggedIn />
    <aside className="sidebar">
      <div className="sidebar-head"><div className="brand"><span className="brand-mark"><img src={brandIcon} alt="" /></span><div className="sidebar-text"><strong>YunZhanCloud</strong><small>IMAGE API CONSOLE</small></div></div><button type="button" className="sidebar-toggle icon-button" aria-label={collapsed ? '展开侧栏' : '收起侧栏'} title={collapsed ? '展开侧栏' : '收起侧栏'} onClick={toggleSidebar}>{collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}</button></div>
      <nav className="side-nav">{links.map(({ to, label, icon: Icon }) => <NavLink key={to} end={to === '/'} to={to} title={collapsed ? label : undefined} className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}><Icon size={18} /><span className="nav-label">{label}</span></NavLink>)}</nav>
      <div className="sidebar-bottom"><div className="sidebar-text"><div className="sidebar-label">{t('balance')}</div><div className="sidebar-balance">{formatMoney(user.balance)}</div></div><button className="account-button" onClick={signOut} title={t('logout')}><span className="sidebar-text">{user.name || user.email}</span><ArrowRightFromLine size={17} /></button></div>
    </aside>
    <main className="main-area"><Outlet /></main>
  </div>
}
