import { useState, type FormEvent } from 'react'
import { Check, LockKeyhole, UserRound } from 'lucide-react'
import { api } from '../lib/api'
import type { User } from '../types'
import { Notice, PageHeader } from '../components/UI'

export function ProfilePage({ user, onUpdated }: { user: User; onUpdated: () => Promise<void> }) {
  const [name, setName] = useState(user.name)
  const [passwords, setPasswords] = useState({ current_password: '', new_password: '', confirm: '' })
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  async function update(event: FormEvent, payload: object, success: string): Promise<boolean> {
    event.preventDefault(); setError(''); setMessage(''); setBusy(true)
    try { await api('/api/auth/me', { method: 'PATCH', body: JSON.stringify(payload) }); await onUpdated(); setMessage(success); return true }
    catch (reason) { setError((reason as Error).message); return false }
    finally { setBusy(false) }
  }
  function changePassword(event: FormEvent) {
    if (passwords.new_password !== passwords.confirm) { event.preventDefault(); setError('两次输入的新密码不一致'); return }
    void update(event, { current_password: passwords.current_password, new_password: passwords.new_password }, '密码已更新').then(ok => { if (ok) setPasswords({ current_password: '', new_password: '', confirm: '' }) })
  }
  return <div className="page"><PageHeader title="用户管理" subtitle="个人信息" />{error && <Notice text={error} error />}{message && <Notice text={message} />}
    <div className="profile-grid"><section><h2><UserRound size={18} />基本信息</h2><form className="stack-form" onSubmit={event => void update(event, { name }, '名称已更新')}><label>邮箱<input value={user.email} disabled /></label><label>名称<input required maxLength={80} value={name} onChange={event => setName(event.target.value)} /></label><button className="button primary" disabled={busy || name.trim() === user.name}><Check size={16} />保存名称</button></form></section>
      <section><h2><LockKeyhole size={18} />修改密码</h2><form className="stack-form" onSubmit={changePassword}><label>当前密码<input required type="password" autoComplete="current-password" value={passwords.current_password} onChange={event => setPasswords({ ...passwords, current_password: event.target.value })} /></label><label>新密码<input required type="password" autoComplete="new-password" minLength={12} maxLength={200} value={passwords.new_password} onChange={event => setPasswords({ ...passwords, new_password: event.target.value })} /></label><label>确认新密码<input required type="password" autoComplete="new-password" minLength={12} value={passwords.confirm} onChange={event => setPasswords({ ...passwords, confirm: event.target.value })} /></label><button className="button primary" disabled={busy}><Check size={16} />更新密码</button></form></section></div>
  </div>
}
