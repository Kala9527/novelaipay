import { useEffect, useState, type FormEvent } from 'react'
import { Plus, RefreshCw } from 'lucide-react'
import { api, formatMoney, post } from '../lib/api'
import type { Job, Mapping, Upstream } from '../types'
import { Empty, Notice, PageHeader, Status } from '../components/UI'
import { UserManagement } from '../components/UserManagement'

type Tab = 'models' | 'accounts' | 'users' | 'reconcile'

export function AdminPage() {
  const [tab, setTab] = useState<Tab>('models')
  const [upstreams, setUpstreams] = useState<Upstream[]>([])
  const [mappings, setMappings] = useState<Mapping[]>([])
  const [uncertain, setUncertain] = useState<Job[]>([])
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [account, setAccount] = useState({ name: '', base_url: '', api_key: '' })
  const [mapping, setMapping] = useState({ public_name: '', upstream_account_id: '', upstream_model: '', price: '', max_concurrency: '2', enabled: true })
  const [resolution, setResolution] = useState<Record<string, string>>({})

  function load() {
    api<Upstream[]>('/api/admin/upstreams').then(setUpstreams).catch(e => setError(e.message))
    api<Mapping[]>('/api/admin/mappings').then(setMappings).catch(e => setError(e.message))
    api<Job[]>('/api/admin/uncertain').then(setUncertain).catch(e => setError(e.message))
  }
  useEffect(() => { load() }, [])

  async function submit(path: string, data: unknown, done?: () => void) {
    setError(''); setMessage('')
    try { await post(path, data); setMessage('操作成功'); done?.(); load() }
    catch (e) { setError((e as Error).message) }
  }

  function saveMapping(event: FormEvent) {
    event.preventDefault()
    submit('/api/admin/mappings', { ...mapping, upstream_account_id: Number(mapping.upstream_account_id), max_concurrency: Number(mapping.max_concurrency) },
      () => setMapping({ public_name: '', upstream_account_id: '', upstream_model: '', price: '', max_concurrency: '2', enabled: true }))
  }

  function editMapping(row: Mapping) {
    setMapping({ public_name: row.public_name, upstream_account_id: String(row.upstream_account_id), upstream_model: row.upstream_model,
      price: row.price || '', max_concurrency: String(row.max_concurrency), enabled: row.enabled })
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  return <div className="page">
    <PageHeader title="管理设置" subtitle="配置上游、公开模型和账户" action={<button className="button secondary" onClick={load}><RefreshCw size={16} />刷新</button>} />
    <div className="tabs">{([['models', '模型与定价'], ['accounts', '上游账户'], ['users', '用户与余额'], ['reconcile', `待核对 (${uncertain.length})`]] as [Tab, string][]).map(([key, label]) => <button key={key} className={tab === key ? 'tab active' : 'tab'} onClick={() => setTab(key)}>{label}</button>)}</div>
    {error && <Notice text={error} error />}{message && <Notice text={message} />}

    {tab === 'models' && <>
      <div className="section-head"><h2>发布模型</h2></div>
      <form className="form-grid" onSubmit={saveMapping}>
        <label>公开模型名<input required value={mapping.public_name} onChange={e => setMapping({ ...mapping, public_name: e.target.value })} placeholder="illustration-pro" /></label>
        <label>上游账户<select required value={mapping.upstream_account_id} onChange={e => setMapping({ ...mapping, upstream_account_id: e.target.value })}><option value="">选择账户</option>{upstreams.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}</select></label>
        <label>上游模型名<input required value={mapping.upstream_model} onChange={e => setMapping({ ...mapping, upstream_model: e.target.value })} placeholder="gpt-image-1" /></label>
        <label>单次价格 (CNY)<input type="number" step="0.0001" min="0.0001" required value={mapping.price} onChange={e => setMapping({ ...mapping, price: e.target.value })} /></label>
        <label>模型并发上限<input type="number" min="1" max="100" required value={mapping.max_concurrency} onChange={e => setMapping({ ...mapping, max_concurrency: e.target.value })} /></label>
        <label className="check-label"><input type="checkbox" checked={mapping.enabled} onChange={e => setMapping({ ...mapping, enabled: e.target.checked })} />启用</label>
        <button className="button primary"><Plus size={16} />保存模型</button>
      </form>
      <div className="section-head"><h2>模型列表</h2></div>
      {mappings.length ? <div className="table-scroll"><table><thead><tr><th>公开名称</th><th>上游模型</th><th>价格</th><th>版本</th><th>状态</th><th></th></tr></thead><tbody>{mappings.map(row => <tr key={row.id}><td>{row.public_name}</td><td>{row.upstream_model}</td><td>{formatMoney(row.price || 0)}</td><td>v{row.revision}</td><td>{row.enabled ? '启用' : '停用'}</td><td className="right"><button className="text-link" onClick={() => editMapping(row)}>编辑</button></td></tr>)}</tbody></table></div> : <Empty text="尚未创建模型" />}
    </>}

    {tab === 'accounts' && <>
      <div className="section-head"><h2>添加上游账户</h2></div>
      <form className="form-grid" onSubmit={e => { e.preventDefault(); submit('/api/admin/upstreams', account, () => setAccount({ name: '', base_url: '', api_key: '' })) }}>
        <label>账户名称<input required value={account.name} onChange={e => setAccount({ ...account, name: e.target.value })} /></label>
        <label>API 基础地址<input required type="url" value={account.base_url} onChange={e => setAccount({ ...account, base_url: e.target.value })} placeholder="https://api.example.com/v1" /></label>
        <label className="wide">上游密钥<input required type="password" autoComplete="off" value={account.api_key} onChange={e => setAccount({ ...account, api_key: e.target.value })} /></label>
        <button className="button primary"><Plus size={16} />添加账户</button>
      </form>
      <div className="section-head"><h2>账户列表</h2></div>
      {upstreams.length ? <div className="table-scroll"><table><thead><tr><th>名称</th><th>基础地址</th><th>状态</th></tr></thead><tbody>{upstreams.map(row => <tr key={row.id}><td>{row.name}</td><td className="mono">{row.base_url}</td><td>{row.enabled ? '启用' : '停用'}</td></tr>)}</tbody></table></div> : <Empty text="尚未添加上游账户" />}
    </>}

    {tab === 'users' && <UserManagement />}

    {tab === 'reconcile' && (uncertain.length ? uncertain.map(job => <div className="reconcile-row" key={job.id}>
      <div><strong className="mono">{job.id}</strong><span>{job.model} · <Status value={job.status} /></span><p>{job.error}</p></div>
      <input placeholder="成功时填写图片 URL" value={resolution[job.id] || ''} onChange={e => setResolution({ ...resolution, [job.id]: e.target.value })} />
      <div className="button-group"><button className="button secondary" onClick={() => submit(`/api/admin/uncertain/${job.id}/resolve`, { succeeded: false, note: '人工核对：未产生有效结果' })}>释放预留</button><button className="button primary" onClick={() => submit(`/api/admin/uncertain/${job.id}/resolve`, { succeeded: true, image_url: resolution[job.id] })}>确认成功</button></div>
    </div>) : <Empty text="没有待核对任务" />)}
  </div>
}
