import { useEffect, useState, type FormEvent } from 'react'
import { Copy, KeyRound, Plus, Trash2 } from 'lucide-react'
import { api, formatDate, post } from '../lib/api'
import type { Key } from '../types'
import { Empty, Notice, PageHeader } from '../components/UI'

export function KeysPage() {
  const [keys, setKeys] = useState<Key[]>([])
  const [name, setName] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const load = () => api<Key[]>('/api/keys').then(setKeys).catch(e => setError(e.message))
  useEffect(() => { load() }, [])
  async function create(event: FormEvent) {
    event.preventDefault(); setError(''); setMessage('')
    try { await post<Key>('/api/keys', { name }); setName(''); setMessage('密钥已创建，可随时在下方复制。'); load() }
    catch (e) { setError((e as Error).message) }
  }
  async function copy(id: number) {
    setError(''); setMessage('')
    try {
      const secret = await api<{ key: string }>(`/api/keys/${id}/secret`)
      await navigator.clipboard.writeText(secret.key)
      setMessage('密钥已复制到剪贴板')
    } catch (e) { setError((e as Error).message) }
  }
  async function revoke(id: number) {
    if (!window.confirm('撤销后此密钥将立即失效，确定继续？')) return
    try { await api(`/api/keys/${id}`, { method: 'DELETE' }); load() }
    catch (e) { setError((e as Error).message) }
  }
  return <div className="page"><PageHeader title="API 密钥" subtitle="密钥仅显示掩码，复制后可粘贴使用" /><form className="inline-form" onSubmit={create}><label className="grow">密钥名称<input value={name} maxLength={80} required placeholder="例如：生产环境" onChange={e => setName(e.target.value)} /></label><button className="button primary"><Plus size={17} />创建密钥</button></form>{error && <Notice text={error} error />}{message && <Notice text={message} />}<div className="section-head"><h2>有效密钥</h2><span className="muted">{keys.length} 个</span></div>{keys.length ? <div className="table-scroll"><table><thead><tr><th>名称</th><th>密钥</th><th>创建时间</th><th></th></tr></thead><tbody>{keys.map(key => <tr key={key.id}><td><span className="cell-icon"><KeyRound size={16} /></span>{key.name}</td><td className="mono">{key.prefix}••••</td><td>{formatDate(key.created_at)}</td><td className="right"><div className="row-actions"><button className="icon-button" title={key.can_copy ? '复制密钥' : '旧密钥无法恢复，请重新创建'} disabled={!key.can_copy} onClick={() => copy(key.id)}><Copy size={17} /></button><button className="icon-button danger" title="撤销密钥" onClick={() => revoke(key.id)}><Trash2 size={17} /></button></div></td></tr>)}</tbody></table></div> : <Empty text="暂无有效密钥" />}</div>
}
