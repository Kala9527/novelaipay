import { useEffect, useState, type FormEvent } from 'react'
import { ArrowRight, LockKeyhole, Mail, Sparkles } from 'lucide-react'
import { api, post } from '../lib/api'
import { Notice } from '../components/UI'
import { PublicHeader } from '../components/PublicHeader'

export function LoginPage({ onLogin }: { onLogin: () => void }) {
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
    <div className="login-main"><div className="login-intro"><div className="login-kicker"><Sparkles size={15} /> NOVELAI IMAGE STUDIO</div><h2>让想象<br /><em>成为画面。</em></h2><p>创作、查看与管理你的每一张生成图片。</p><div className="login-art" aria-hidden="true"><span className="login-art-frame frame-one" /><span className="login-art-frame frame-two" /><span className="login-art-frame frame-three" /></div></div>
    <div className="login-content">
      <div className="login-kicker"><LockKeyhole size={15} /> ACCOUNT ACCESS</div>
      <h1>{mode === 'login' ? '欢迎回来' : '创建账户'}</h1>
      <p>{mode === 'login' ? '登录后继续创作。' : '注册后即可创建独立的 API 密钥。'}</p>
      {registrationEnabled && <div className="auth-modes"><button className={mode === 'login' ? 'active' : ''} type="button" onClick={() => { setMode('login'); setError('') }}>登录</button><button className={mode === 'register' ? 'active' : ''} type="button" onClick={() => { setMode('register'); setError('') }}>注册</button></div>}
      <form className="login-form" onSubmit={submit}>
        {mode === 'register' && <label>名称<input required maxLength={80} autoComplete="name" value={name} onChange={e => setName(e.target.value)} placeholder="你的名称" /></label>}
        <label>邮箱地址<input type="email" autoComplete="username" required value={email} onChange={e => setEmail(e.target.value)} placeholder="name@example.com" /></label>
        {mode === 'register' && <><div className="registration-code-row"><label>邮箱验证码<input required inputMode="numeric" pattern="[0-9]{6}" maxLength={6} autoComplete="one-time-code" value={code} onChange={e => setCode(e.target.value)} placeholder="6 位验证码" /></label><button type="button" className="button secondary" disabled={busy || cooldown > 0 || !emailConfigured || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)} onClick={sendCode}><Mail size={15} />{cooldown > 0 ? `${cooldown}s` : '发送验证码'}</button></div>{codeSent && <span className="registration-hint">验证码已发送，{codeExpiry} 分钟内有效。</span>}{!emailConfigured && <span className="registration-hint">管理员尚未配置通知邮箱，暂时无法注册。</span>}</>}
        <label>密码<input type="password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} required minLength={mode === 'register' ? 12 : 8} value={password} onChange={e => setPassword(e.target.value)} placeholder={mode === 'register' ? '至少 12 个字符' : '输入密码'} /></label>
        {error && <Notice text={error} error />}
        <button className="button primary full" disabled={busy}>{busy ? '请稍候...' : mode === 'login' ? '登录' : '创建账户'}<ArrowRight size={17} /></button>
      </form>
    </div></div>
    <div className="login-footer">YUNZHANCLOUD · IMAGE STUDIO</div>
  </div>
}
