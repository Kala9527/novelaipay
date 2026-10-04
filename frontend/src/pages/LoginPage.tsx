import { useState, type FormEvent } from 'react'
import { Activity, ArrowRight, LockKeyhole } from 'lucide-react'
import { post } from '../lib/api'
import { Notice } from '../components/UI'

export function LoginPage({ onLogin }: { onLogin: () => void }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('')
    try { await post('/api/auth/login', { email, password }); onLogin() }
    catch (err) { setError((err as Error).message) }
    finally { setBusy(false) }
  }
  return <div className="login-shell"><div className="login-top"><span className="brand-mark"><Activity size={20} /></span><strong>Novelaipay</strong></div><div className="login-content"><div className="login-kicker"><LockKeyhole size={16} /> SECURE ACCESS</div><h1>登录控制台</h1><p>管理图像生成 API、任务和资金流水。</p><form className="login-form" onSubmit={submit}><label>邮箱地址<input type="email" autoComplete="username" required value={email} onChange={e => setEmail(e.target.value)} placeholder="name@example.com" /></label><label>密码<input type="password" autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)} placeholder="输入密码" /></label>{error && <Notice text={error} error />}<button className="button primary full" disabled={busy}>{busy ? '登录中...' : '登录'}<ArrowRight size={17} /></button></form></div><div className="login-footer">NOVELAIPAY · IMAGE API INFRASTRUCTURE</div></div>
}
