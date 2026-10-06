import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, Megaphone, Store, X, SunMoon, Languages, BookOpen } from 'lucide-react'
import { api, formatDate } from '../lib/api'
import type { Announcement } from '../types'
import brandIcon from '../assets/brand-icon.svg'
import { usePreferences, type LanguagePreference, type ThemePreference } from '../lib/preferences'

export function PublicHeader({ loggedIn }: { loggedIn: boolean }) {
  const { theme, setTheme, language, setLanguage, t } = usePreferences()
  const [announcements, setAnnouncements] = useState<Announcement[]>([])
  const [open, setOpen] = useState(false)
  const [selected, setSelected] = useState<number | null>(null)
  useEffect(() => {
    const load = () => { api<Announcement[]>('/api/public/announcements').then(setAnnouncements).catch(() => setAnnouncements([])) }
    load()
    window.addEventListener('announcements-changed', load)
    return () => window.removeEventListener('announcements-changed', load)
  }, [loggedIn])
  useEffect(() => {
    if (!open) return
    const close = (event: KeyboardEvent) => { if (event.key === 'Escape') setOpen(false) }
    window.addEventListener('keydown', close)
    return () => window.removeEventListener('keydown', close)
  }, [open])
  const current = announcements.find(item => item.id === selected)
  return <>
    <header className="public-header">
      <Link to={loggedIn ? '/' : '/login'} className="public-brand"><span className="brand-mark"><img src={brandIcon} alt="" /></span><strong>YunZhanCloud</strong></Link>
      <nav className="public-actions" aria-label="页面导航">
        <Link className="header-link header-nav" to="/models"><Store size={17} />{t('models')}</Link>
        {loggedIn && <Link className="header-link header-nav" to="/api-guide"><BookOpen size={17} />{t('docs')}</Link>}
        <button type="button" className="header-link header-icon" aria-label={t('announcements')} title={t('announcements')} onClick={() => { setSelected(null); setOpen(true); api<Announcement[]>('/api/public/announcements').then(setAnnouncements).catch(() => {}) }}><Megaphone size={17} />{announcements.length > 0 && <span className="header-count">{announcements.length}</span>}</button>
        <label className="header-select" title={t('theme')}><SunMoon size={17} /><span className="sr-only">{t('theme')}</span><select aria-label={t('theme')} value={theme} onChange={event => setTheme(event.target.value as ThemePreference)}><option value="system">{t('system')}</option><option value="light">{t('light')}</option><option value="dark">{t('dark')}</option></select></label>
        <label className="header-select" title={t('language')}><Languages size={17} /><span className="sr-only">{t('language')}</span><select aria-label={t('language')} value={language} onChange={event => setLanguage(event.target.value as LanguagePreference)}><option value="auto">{t('auto')}</option><option value="zh">{t('chinese')}</option><option value="en">{t('english')}</option><option value="ja">{t('japanese')}</option></select></label>
        {!loggedIn && <Link className="header-link login-link" to="/login">{t('login')}<ArrowRight size={16} /></Link>}
      </nav>
    </header>
    {open && <div className="dialog-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) setOpen(false) }}>
      <section className="dialog-panel" role="dialog" aria-modal="true" aria-label={t('announcements')} tabIndex={-1}>
        <div className="dialog-heading"><h2>{current ? current.title : t('announcements')}</h2><button type="button" className="icon-button" aria-label={t('close')} title={t('close')} onClick={() => setOpen(false)}><X size={19} /></button></div>
        {current ? <><button type="button" className="text-link" onClick={() => setSelected(null)}>{t('back')}</button><div className="announcement-meta">{current.is_private ? t('members') : t('public')} · {formatDate(current.created_at)}</div><p className="announcement-body">{current.body}</p></> : announcements.length ? <div className="announcement-list">{announcements.map(item => <button key={item.id} type="button" onClick={() => setSelected(item.id)}><strong>{item.title}</strong><span>{item.is_private ? t('members') : t('public')} · {formatDate(item.created_at)}</span></button>)}</div> : <p className="muted">{t('noAnnouncements')}</p>}
      </section>
    </div>}
  </>
}
