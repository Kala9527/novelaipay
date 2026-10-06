import { useEffect, useState, type FormEvent } from 'react'
import { Check, Send } from 'lucide-react'
import { api, post } from '../lib/api'
import { Notice } from './UI'

type Settings = {
  enabled: boolean; smtp_host: string; smtp_port: number; smtp_security: 'ssl' | 'starttls'
  smtp_username: string; smtp_password_configured: boolean; sender_email: string
  subject: string; html_template: string; template_vars: Record<string, string>
  code_expiry_minutes: number; email_configured: boolean
}

export function RegistrationManagement() {
  const [settings, setSettings] = useState<Settings | null>(null)
  const [password, setPassword] = useState('')
  const [variables, setVariables] = useState('')
  const [testRecipient, setTestRecipient] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  useEffect(() => { api<Settings>('/api/admin/registration-settings').then(data => { setSettings(data); setVariables(Object.entries(data.template_vars).map(([key, value]) => `${key}=${value}`).join('\n')); setTestRecipient(data.sender_email) }).catch(e => setError(e.message)) }, [])

  async function save(event: FormEvent) {
    event.preventDefault()
    if (!settings) return
    const template_vars: Record<string, string> = {}
    for (const line of variables.split('\n').map(v => v.trim()).filter(Boolean)) {
      const position = line.indexOf('=')
      if (position < 1) { setError('自定义参数每行使用 key=value 格式'); return }
      template_vars[line.slice(0, position).trim()] = line.slice(position + 1).trim()
    }
    setBusy(true); setError(''); setMessage('')
    try {
      const result = await api<Settings>('/api/admin/registration-settings', { method: 'PUT', body: JSON.stringify({ ...settings, smtp_password: password || null, template_vars }) })
      setSettings(result); setPassword(''); setMessage('设置已保存')
    } catch (e) { setError((e as Error).message) }
    finally { setBusy(false) }
  }

  async function sendTest() {
    setBusy(true); setError(''); setMessage('')
    try { await post(`/api/admin/registration-settings/test?recipient=${encodeURIComponent(testRecipient)}`, {}); setMessage(`测试邮件已发送至 ${testRecipient}`) }
    catch (e) { setError((e as Error).message) }
    finally { setBusy(false) }
  }

  if (!settings) return error ? <Notice text={error} error /> : null
  const update = (patch: Partial<Settings>) => setSettings({ ...settings, ...patch })
  return <div className="registration-management">
    <div className="admin-toolbar"><div><h2>登录与注册</h2><span>{settings.enabled ? '注册开放' : '注册关闭'}</span></div></div>
    {error && <Notice text={error} error />}{message && <Notice text={message} />}
    <form className="form-grid registration-settings-form" onSubmit={save}>
      <label className="check-label wide"><input type="checkbox" checked={settings.enabled} onChange={e => update({ enabled: e.target.checked })} />开放新用户注册</label>
      <label>SMTP 服务器<input value={settings.smtp_host} onChange={e => update({ smtp_host: e.target.value })} placeholder="smtp.qq.com" /></label>
      <label>端口<input type="number" required min={1} max={65535} value={settings.smtp_port} onChange={e => update({ smtp_port: Number(e.target.value) })} /></label>
      <label>加密方式<select value={settings.smtp_security} onChange={e => update({ smtp_security: e.target.value as Settings['smtp_security'] })}><option value="ssl">SSL/TLS</option><option value="starttls">STARTTLS</option></select></label>
      <label>SMTP 用户名<input value={settings.smtp_username} onChange={e => update({ smtp_username: e.target.value })} placeholder="example@qq.com" /></label>
      <label>SMTP 授权码<input type="password" autoComplete="new-password" value={password} onChange={e => setPassword(e.target.value)} placeholder={settings.smtp_password_configured ? '已配置，留空则保持不变' : '输入授权码'} /></label>
      <label>发件邮箱<input type="email" value={settings.sender_email} onChange={e => update({ sender_email: e.target.value })} placeholder="example@qq.com" /></label>
      <label>验证码有效时间（分钟）<input type="number" required min={1} max={60} value={settings.code_expiry_minutes} onChange={e => update({ code_expiry_minutes: Number(e.target.value) })} /></label>
      <label className="wide">邮件主题<input required value={settings.subject} onChange={e => update({ subject: e.target.value })} /></label>
      <label className="wide">邮件 HTML 内容<textarea rows={12} required value={settings.html_template} onChange={e => update({ html_template: e.target.value })} /></label>
      <div className="registration-template-help">占位符：<code>{'{{code}}'}</code>、<code>{'{{email}}'}</code>、<code>{'{{expires_minutes}}'}</code>、<code>{'{{expires_at}}'}</code>。自定义参数填写后可在 HTML 中使用同名占位符；值会按 HTML 文本转义。</div>
      <label className="wide">自定义参数（每行 key=value）<textarea rows={4} value={variables} onChange={e => setVariables(e.target.value)} placeholder="site_name=NovelAI Pay" /></label>
      <div className="admin-form-actions"><button className="button primary" disabled={busy}><Check size={16} />保存设置</button></div>
    </form>
    <div className="registration-test"><label>测试收件邮箱<input type="email" value={testRecipient} onChange={e => setTestRecipient(e.target.value)} /></label><button type="button" className="button secondary" disabled={busy || !settings.email_configured || !testRecipient} onClick={sendTest}><Send size={16} />发送测试邮件</button></div>
  </div>
}
