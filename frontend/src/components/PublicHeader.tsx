import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, Megaphone, Store, X } from 'lucide-react'
import { api, formatDate } from '../lib/api'
import type { Announcement } from '../types'
import brandIcon from '../assets/brand-icon.svg'

export function PublicHeader({ loggedIn }: { loggedIn: boolean }) {
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
        <button type="button" className="header-link" onClick={() => { setSelected(null); setOpen(true); api<Announcement[]>('/api/public/announcements').then(setAnnouncements).catch(() => {}) }}><Megaphone size={17} />公告{announcements.length > 0 && <span className="header-count">{announcements.length}</span>}</button>
        <Link className="header-link" to="/models"><Store size={17} />模型广场</Link>
        {!loggedIn && <Link className="header-link login-link" to="/login">登录<ArrowRight size={16} /></Link>}
      </nav>
    </header>
    {open && <div className="dialog-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) setOpen(false) }}>
      <section className="dialog-panel" role="dialog" aria-modal="true" aria-label="公告" tabIndex={-1}>
        <div className="dialog-heading"><h2>{current ? current.title : '公告'}</h2><button type="button" className="icon-button" aria-label="关闭公告" title="关闭公告" onClick={() => setOpen(false)}><X size={19} /></button></div>
        {current ? <><button type="button" className="text-link" onClick={() => setSelected(null)}>返回公告列表</button><div className="announcement-meta">{current.is_private ? '登录用户' : '公开'} · {formatDate(current.created_at)} 北京时间</div><p className="announcement-body">{current.body}</p></> : announcements.length ? <div className="announcement-list">{announcements.map(item => <button key={item.id} type="button" onClick={() => setSelected(item.id)}><strong>{item.title}</strong><span>{item.is_private ? '登录用户' : '公开'} · {formatDate(item.created_at)}</span></button>)}</div> : <p className="muted">暂无有效公告</p>}
      </section>
    </div>}
  </>
}
