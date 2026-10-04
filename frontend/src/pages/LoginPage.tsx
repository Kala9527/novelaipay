import { useEffect, useState, type FormEvent } from 'react'
import { Activity, ArrowRight, LockKeyhole } from 'lucide-react'
import { api, post } from '../lib/api'
import { Notice } from '../components/UI'

export function LoginPage({ onLogin }: { onLogin: () => void }) {
  const [registrationEnabled, setRegistrationEnabled] = useState(false)
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => { api<{ registration_enabled: boolean }>('/api/auth/options').then(data => setRegistrationEnabled(data.registration_enabled)).catch(() => {}) }, [])

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      await post(`/api/auth/${mode === 'login' ? 'login' : 'register'}`, mode === 'login' ? { email, password } : { name, email, password })
      onLogin()
    }
    catch (err) { setError((err as Error).message) }
    finally { setBusy(false) }
  }
  return <div className="login-shell">
    <div className="login-top"><span className="brand-mark"><Activity size={20} /></span><strong>Novelaipay</strong></div>
    <div className="login-content">
      <div className="login-kicker"><LockKeyhole size={16} /> SECURE ACCESS</div>
      <h1>{mode === 'login' ? '登录控制台' : '创建账户'}</h1>
      <p>{mode === 'login' ? '管理图像生成 API、任务和资金流水。' : '注册后即可创建独立的 API 密钥。'}</p>
      {registrationEnabled && <div className="auth-modes"><button className={mode === 'login' ? 'active' : ''} type="button" onClick={() => { setMode('login'); setError('') }}>登录</button><button className={mode === 'register' ? 'active' : ''} type="button" onClick={() => { setMode('register'); setError('') }}>注册</button></div>}
      <form className="login-form" onSubmit={submit}>
        {mode === 'register' && <label>名称<input required maxLength={80} autoComplete="name" value={name} onChange={e => setName(e.target.value)} placeholder="你的名称" /></label>}
        <label>邮箱地址<input type="email" autoComplete="username" required value={email} onChange={e => setEmail(e.target.value)} placeholder="name@example.com" /></label>
        <label>密码<input type="password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} required minLength={mode === 'register' ? 12 : 8} value={password} onChange={e => setPassword(e.target.value)} placeholder={mode === 'register' ? '至少 12 个字符' : '输入密码'} /></label>
        {error && <Notice text={error} error />}
        <button className="button primary full" disabled={busy}>{busy ? '请稍候...' : mode === 'login' ? '登录' : '创建账户'}<ArrowRight size={17} /></button>
      </form>
    </div>
    <div className="login-footer">NOVELAIPAY · IMAGE API INFRASTRUCTURE</div>
  </div>
}
