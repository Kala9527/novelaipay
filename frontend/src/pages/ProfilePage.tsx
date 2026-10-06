import { useState, type FormEvent } from 'react'
import { Check, LockKeyhole, UserRound } from 'lucide-react'
import { api } from '../lib/api'
import type { User } from '../types'
import { Notice, PageHeader } from '../components/UI'
import { usePreferences } from '../lib/preferences'

export function ProfilePage({ user, onUpdated }: { user: User; onUpdated: () => Promise<void> }) {
  const { t } = usePreferences()
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
    if (passwords.new_password !== passwords.confirm) { event.preventDefault(); setError(t('passwordMismatch')); return }
    void update(event, { current_password: passwords.current_password, new_password: passwords.new_password }, t('passwordSaved')).then(ok => { if (ok) setPasswords({ current_password: '', new_password: '', confirm: '' }) })
  }
  return <div className="page"><PageHeader title={t('profile')} subtitle={t('profileSubtitle')} />{error && <Notice text={error} error />}{message && <Notice text={message} />}
    <div className="profile-grid"><section><h2><UserRound size={18} />{t('basicInfo')}</h2><form className="stack-form" onSubmit={event => void update(event, { name }, t('nameSaved'))}><label>{t('email')}<input value={user.email} disabled /></label><label>{t('name')}<input required maxLength={80} value={name} onChange={event => setName(event.target.value)} /></label><button className="button primary" disabled={busy || name.trim() === user.name}><Check size={16} />{t('saveName')}</button></form></section>
      <section><h2><LockKeyhole size={18} />{t('updatePassword')}</h2><form className="stack-form" onSubmit={changePassword}><label>{t('currentPassword')}<input required type="password" autoComplete="current-password" value={passwords.current_password} onChange={event => setPasswords({ ...passwords, current_password: event.target.value })} /></label><label>{t('newPassword')}<input required type="password" autoComplete="new-password" minLength={12} maxLength={200} value={passwords.new_password} onChange={event => setPasswords({ ...passwords, new_password: event.target.value })} /></label><label>{t('confirmPassword')}<input required type="password" autoComplete="new-password" minLength={12} value={passwords.confirm} onChange={event => setPasswords({ ...passwords, confirm: event.target.value })} /></label><button className="button primary" disabled={busy}><Check size={16} />{t('savePassword')}</button></form></section></div>
  </div>
}
