import { useEffect, useState, type FormEvent } from 'react'
import { ArrowRight, LockKeyhole, Mail, Sparkles } from 'lucide-react'
import { api, post } from '../lib/api'
import { Notice } from '../components/UI'
import { PublicHeader } from '../components/PublicHeader'
import { Link } from 'react-router-dom'
import { usePreferences } from '../lib/preferences'
import { WelcomeCarousel } from '../components/WelcomeCarousel'

export function LoginPage({ onLogin }: { onLogin: () => void }) {
  const { t } = usePreferences()
  const [registrationEnabled, setRegistrationEnabled] = useState(false)
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [emailConfigured, setEmailConfigured] = useState(false)
  const [codeExpiry, setCodeExpiry] = useState(15)
  const [codeSent, setCodeSent] = useState(false)
  const [cooldown, setCooldown] = useState(0)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => { api<{ registration_enabled: boolean; email_configured: boolean; code_expiry_minutes: number }>('/api/auth/options').then(data => { setRegistrationEnabled(data.registration_enabled); setEmailConfigured(data.email_configured); setCodeExpiry(data.code_expiry_minutes) }).catch(() => {}) }, [])
  useEffect(() => { if (cooldown > 0) { const timer = window.setTimeout(() => setCooldown(cooldown - 1), 1000); return () => window.clearTimeout(timer) } }, [cooldown])

  async function sendCode() {
    setError(''); setBusy(true)
    try { await post('/api/auth/registration-code', { email }); setCodeSent(true); setCooldown(60) }
    catch (err) { setError((err as Error).message) }
    finally { setBusy(false) }
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      await post(`/api/auth/${mode === 'login' ? 'login' : 'register'}`, mode === 'login' ? { email, password } : { name, email, password, code })
      onLogin()
    }
    catch (err) { setError((err as Error).message) }
    finally { setBusy(false) }
  }
  return <div className="login-shell">
    <PublicHeader loggedIn={false} />
    <div className="login-main"><div className="login-intro"><div className="login-kicker"><Sparkles size={15} /> YUNZHANCLOUD · IMAGE API</div><h2>{t('loginHeroTitle')}</h2><p>{t('loginHeroBody')}</p><div className="login-intro-actions"><Link to="/models" className="button secondary">{t('exploreModels')}<ArrowRight size={16} /></Link><a href="#login-form" className="text-link">{t('jumpIn')}<ArrowRight size={16} /></a></div><WelcomeCarousel /></div>
    <div className="login-content">
      <div className="login-kicker"><LockKeyhole size={15} /> ACCOUNT ACCESS</div>
      <h1>{mode === 'login' ? t('welcome') : t('createAccount')}</h1>
      <p>{mode === 'login' ? t('loginSubtitle') : t('registerSubtitle')}</p>
      {registrationEnabled && <div className="auth-modes"><button className={mode === 'login' ? 'active' : ''} type="button" onClick={() => { setMode('login'); setError('') }}>{t('login')}</button><button className={mode === 'register' ? 'active' : ''} type="button" onClick={() => { setMode('register'); setError('') }}>{t('register')}</button></div>}
      <form id="login-form" className="login-form" onSubmit={submit}>
        {mode === 'register' && <label>{t('name')}<input required maxLength={80} autoComplete="name" value={name} onChange={e => setName(e.target.value)} placeholder={t('namePlaceholder')} /></label>}
        <label>{t('email')}<input type="email" autoComplete="username" required value={email} onChange={e => setEmail(e.target.value)} placeholder="name@example.com" /></label>
        {mode === 'register' && <><div className="registration-code-row"><label>{t('emailCode')}<input required inputMode="numeric" pattern="[0-9]{6}" maxLength={6} autoComplete="one-time-code" value={code} onChange={e => setCode(e.target.value)} placeholder={t('codePlaceholder')} /></label><button type="button" className="button secondary" disabled={busy || cooldown > 0 || !emailConfigured || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)} onClick={sendCode}><Mail size={15} />{cooldown > 0 ? `${cooldown}s` : t('sendCode')}</button></div>{codeSent && <span className="registration-hint">{t('codeSent', { minutes: codeExpiry })}</span>}{!emailConfigured && <span className="registration-hint">{t('registrationUnavailable')}</span>}</>}
        <label>{t('password')}<input type="password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} required minLength={mode === 'register' ? 12 : 8} value={password} onChange={e => setPassword(e.target.value)} placeholder={mode === 'register' ? t('keyPlaceholder') : t('passwordPlaceholder')} /></label>
        {error && <Notice text={error} error />}
        <button className="button primary full" disabled={busy}>{busy ? t('wait') : mode === 'login' ? t('login') : t('create')}<ArrowRight size={17} /></button>
      </form>
    </div></div>
    <div className="login-footer">YUNZHANCLOUD · IMAGE STUDIO</div>
  </div>
}
