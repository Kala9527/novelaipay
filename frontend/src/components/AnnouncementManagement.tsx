import { useEffect, useState, type FormEvent } from 'react'
import { Check, Pencil, Plus, Trash2, X } from 'lucide-react'
import { api, beijingInput, beijingToUtc, formatDate, post } from '../lib/api'
import type { Announcement } from '../types'
import { Empty, Notice } from './UI'

const blank = () => ({ id: null as number | null, title: '', body: '', is_private: false, starts_at: '', ends_at: '' })

export function AnnouncementManagement() {
  const [rows, setRows] = useState<Announcement[]>([])
  const [editor, setEditor] = useState(blank)
  const [open, setOpen] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  function load() { api<Announcement[]>('/api/admin/announcements').then(setRows).catch(reason => setError(reason.message)) }
  useEffect(() => { load() }, [])
  function edit(row: Announcement) { setEditor({ id: row.id, title: row.title, body: row.body, is_private: row.is_private, starts_at: beijingInput(row.starts_at), ends_at: beijingInput(row.ends_at) }); setOpen(true) }
  async function save(event: FormEvent) {
    event.preventDefault(); setError(''); setMessage('')
    if (editor.starts_at && editor.ends_at && editor.ends_at <= editor.starts_at) { setError('结束时间必须晚于开始时间'); return }
    const payload = { title: editor.title, body: editor.body, is_private: editor.is_private,
      starts_at: beijingToUtc(editor.starts_at), ends_at: beijingToUtc(editor.ends_at) }
    try {
      if (editor.id) await api(`/api/admin/announcements/${editor.id}`, { method: 'PATCH', body: JSON.stringify(payload) })
      else await post('/api/admin/announcements', payload)
      setOpen(false); setEditor(blank()); setMessage('公告已保存'); load(); window.dispatchEvent(new Event('announcements-changed'))
    } catch (reason) { setError((reason as Error).message) }
  }
  async function remove(row: Announcement) {
    if (!window.confirm(`删除公告“${row.title}”？`)) return
    setError(''); setMessage('')
    try { await api(`/api/admin/announcements/${row.id}`, { method: 'DELETE' }); setMessage('公告已删除'); load(); window.dispatchEvent(new Event('announcements-changed')) }
    catch (reason) { setError((reason as Error).message) }
  }
  return <div><div className="admin-toolbar"><div><h2>公告管理</h2><span>{rows.length} 项</span></div><button type="button" className="button primary" onClick={() => { setEditor(blank()); setOpen(true) }}><Plus size={16} />发布公告</button></div>
    {error && <Notice text={error} error />}{message && <Notice text={message} />}
    {open && <section className="admin-edit-section"><div className="admin-edit-heading"><h3>{editor.id ? '编辑公告' : '发布公告'}</h3><button type="button" className="icon-button" title="关闭" onClick={() => setOpen(false)}><X size={17} /></button></div><form className="announcement-form" onSubmit={save}><label>标题<input required maxLength={120} value={editor.title} onChange={event => setEditor({ ...editor, title: event.target.value })} /></label><label>正文<textarea required maxLength={10000} rows={6} value={editor.body} onChange={event => setEditor({ ...editor, body: event.target.value })} /></label><div className="announcement-form-row"><label>可见范围<select value={editor.is_private ? 'private' : 'public'} onChange={event => setEditor({ ...editor, is_private: event.target.value === 'private' })}><option value="public">公开公告</option><option value="private">仅登录用户</option></select></label><label>开始时间（北京时间）<input type="datetime-local" value={editor.starts_at} onChange={event => setEditor({ ...editor, starts_at: event.target.value })} /></label><label>结束时间（北京时间）<input type="datetime-local" value={editor.ends_at} onChange={event => setEditor({ ...editor, ends_at: event.target.value })} /></label></div><div className="admin-form-actions"><button className="button primary"><Check size={16} />保存公告</button><button type="button" className="button secondary" onClick={() => setOpen(false)}>取消</button></div></form></section>}
    {rows.length ? <div className="table-scroll admin-table"><table><thead><tr><th>标题</th><th>范围</th><th>生效时间（北京时间）</th><th>失效时间（北京时间）</th><th className="right">操作</th></tr></thead><tbody>{rows.map(row => <tr key={row.id}><td><strong>{row.title}</strong><small className="announcement-preview">{row.body}</small></td><td>{row.is_private ? '仅登录用户' : '公开'}</td><td>{row.starts_at ? formatDate(row.starts_at) : '立即'}</td><td>{row.ends_at ? formatDate(row.ends_at) : '长期有效'}</td><td className="right"><div className="admin-row-actions"><button className="icon-button" title="编辑公告" onClick={() => edit(row)}><Pencil size={16} /></button><button className="icon-button danger" title="删除公告" onClick={() => remove(row)}><Trash2 size={16} /></button></div></td></tr>)}</tbody></table></div> : <Empty text="暂无公告" />}
  </div>
}
