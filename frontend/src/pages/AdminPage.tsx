import { useEffect, useState, type FormEvent } from 'react'
import { Plus, RefreshCw } from 'lucide-react'
import { api, formatMoney, post } from '../lib/api'
import type { Group, GroupRecipient, Job, Mapping, Upstream } from '../types'
import { Empty, Notice, PageHeader, Status } from '../components/UI'
import { UserManagement } from '../components/UserManagement'

type Tab = 'models' | 'groups' | 'accounts' | 'users' | 'reconcile'

export function AdminPage() {
  const [tab, setTab] = useState<Tab>('models')
  const [upstreams, setUpstreams] = useState<Upstream[]>([])
  const [groups, setGroups] = useState<Group[]>([])
  const [catalogs, setCatalogs] = useState<Record<number, string[]>>({})
  const [group, setGroup] = useState({ id: null as number | null, name: '', max_concurrency: 10, account_ids: [] as number[], member_ids: [] as number[], is_private: false, enabled: true })
  const [recipients, setRecipients] = useState<GroupRecipient[]>([])
  const [groupId, setGroupId] = useState('')
  const [extraRoutes, setExtraRoutes] = useState<{ account_id: number; upstream_model: string }[]>([])
  const [mappings, setMappings] = useState<Mapping[]>([])
  const [uncertain, setUncertain] = useState<Job[]>([])
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [account, setAccount] = useState({ name: '', base_url: 'https://image.novelai.net', api_key: '', provider: 'novelai', opus_free: false, max_concurrency: 10 })
  const [mapping, setMapping] = useState({ public_name: '', upstream_account_id: '', upstream_model: '', price: '', extra_amount: '0.1', max_concurrency: '2', enabled: true })
  const [resolution, setResolution] = useState<Record<string, string>>({})
  const [resolutionAnlas, setResolutionAnlas] = useState<Record<string, string>>({})

  function load() {
    api<Upstream[]>('/api/admin/upstreams').then(setUpstreams).catch(e => setError(e.message))
    api<Group[]>('/api/admin/groups').then(setGroups).catch(e => setError(e.message))
    api<GroupRecipient[]>('/api/admin/group-recipients').then(setRecipients).catch(e => setError(e.message))
    api<Mapping[]>('/api/admin/mappings').then(setMappings).catch(e => setError(e.message))
    api<Job[]>('/api/admin/uncertain').then(setUncertain).catch(e => setError(e.message))
  }
  useEffect(() => { load() }, [])

  async function submit(path: string, data: unknown, done?: () => void) {
    setError(''); setMessage('')
    try { await post(path, data); setMessage('操作成功'); done?.(); load() }
    catch (e) { setError((e as Error).message) }
  }

  async function fetchModels(id: number) {
    try { const result = await api<{ models: string[] }>(`/api/admin/upstreams/${id}/models`); setCatalogs(current => ({ ...current, [id]: result.models })) }
    catch (e) { setError((e as Error).message) }
  }

  async function updateAccount(row: Upstream, max_concurrency: number, enabled = row.enabled) {
    try { await api(`/api/admin/upstreams/${row.id}`, { method: 'PATCH', body: JSON.stringify({ max_concurrency, enabled }) }); load() }
    catch (e) { setError((e as Error).message) }
  }

  async function createAccount(event: FormEvent) {
    event.preventDefault(); setError(''); setMessage('')
    try {
      const created = await post<Upstream>('/api/admin/upstreams', account)
      setAccount({ name: '', base_url: 'https://image.novelai.net', api_key: '', provider: 'novelai', opus_free: false, max_concurrency: 10 })
      setMessage('账户已添加，正在获取模型')
      load()
      await fetchModels(created.id)
    } catch (e) { setError((e as Error).message) }
  }

  function saveMapping(event: FormEvent) {
    event.preventDefault()
    const provider = upstreams.find(row => row.id === Number(mapping.upstream_account_id))?.provider
    submit('/api/admin/mappings', { ...mapping, group_id: Number(groupId), routes: [{ account_id: Number(mapping.upstream_account_id), upstream_model: mapping.upstream_model }, ...extraRoutes], extra_amount: provider === 'novelai' ? mapping.extra_amount : '0', upstream_account_id: Number(mapping.upstream_account_id) },
      () => { setMapping({ public_name: '', upstream_account_id: '', upstream_model: '', price: '', extra_amount: '0.1', max_concurrency: '2', enabled: true }); setExtraRoutes([]) })
  }

  function editMapping(row: Mapping) {
    setGroupId(String(row.group_id))
    setExtraRoutes(row.routes.slice(1))
    setMapping({ public_name: row.public_name, upstream_account_id: String(row.upstream_account_id), upstream_model: row.upstream_model,
      price: row.price || '', extra_amount: row.extra_amount || '0', max_concurrency: String(row.max_concurrency), enabled: row.enabled })
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const selectedGroup = groups.find(row => row.id === Number(groupId))
  const availableAccounts = upstreams.filter(row => selectedGroup?.account_ids.includes(row.id))
  const canAddBackup = !!mapping.upstream_account_id && extraRoutes.length < availableAccounts.length - 1

  return <div className="page">
    <PageHeader title="管理设置" subtitle="配置分组、上游和模型定价" action={<button className="button secondary" onClick={load}><RefreshCw size={16} />刷新</button>} />
    <div className="tabs">{([['models', '模型与定价'], ['groups', '分组'], ['accounts', '上游账户'], ['users', '用户与余额'], ['reconcile', `待核对 (${uncertain.length})`]] as [Tab, string][]).map(([key, label]) => <button key={key} className={tab === key ? 'tab active' : 'tab'} onClick={() => setTab(key)}>{label}</button>)}</div>
    {error && <Notice text={error} error />}{message && <Notice text={message} />}

    {tab === 'groups' && <>
      <div className="section-head"><h2>分组配置</h2></div>
      <form className="form-grid" onSubmit={e => { e.preventDefault(); submit('/api/admin/groups', group, () => setGroup({ id: null, name: '', max_concurrency: 10, account_ids: [], member_ids: [], is_private: false, enabled: true })) }}>
        <label>分组名称<input required value={group.name} onChange={e => setGroup({ ...group, name: e.target.value })} /></label>
        <label>最大并发数<input type="number" min="1" max="1000" required value={group.max_concurrency} onChange={e => setGroup({ ...group, max_concurrency: Number(e.target.value) })} /></label>
        <div className="wide"><strong>上游账号</strong><div className="button-group">{upstreams.map(row => <label className="check-label" key={row.id}><input type="checkbox" checked={group.account_ids.includes(row.id)} onChange={e => setGroup(current => ({ ...current, account_ids: e.target.checked ? [...current.account_ids, row.id] : current.account_ids.filter(id => id !== row.id) }))} />{row.name}</label>)}</div></div>
        <label>可见范围<select value={group.is_private ? 'private' : 'public'} onChange={e => setGroup({ ...group, is_private: e.target.value === 'private', member_ids: [] })}><option value="public">公开</option><option value="private">专属</option></select></label>
        {group.is_private && <div className="wide"><strong>授权用户</strong><div className="button-group">{recipients.map(row => <label className="check-label" key={row.id}><input type="checkbox" checked={group.member_ids.includes(row.id)} onChange={e => setGroup(current => ({ ...current, member_ids: e.target.checked ? [...current.member_ids, row.id] : current.member_ids.filter(id => id !== row.id) }))} />{row.name || row.email}{row.is_admin ? '（管理员）' : ''}</label>)}</div></div>}
        <label className="check-label"><input type="checkbox" checked={group.enabled} onChange={e => setGroup({ ...group, enabled: e.target.checked })} />启用</label>
        <button className="button primary" disabled={group.is_private && !group.member_ids.length}><Plus size={16} />保存分组</button>
        {group.id && <button type="button" className="button secondary" onClick={() => setGroup({ id: null, name: '', max_concurrency: 10, account_ids: [], member_ids: [], is_private: false, enabled: true })}>取消编辑</button>}
      </form>
      {groups.length ? <div className="table-scroll"><table><thead><tr><th>分组</th><th>范围</th><th>上游账号</th><th>最大并发</th><th>状态</th><th></th></tr></thead><tbody>{groups.map(row => <tr key={row.id}><td>{row.name}</td><td>{row.is_private ? `专属 · ${row.member_ids.length} 人` : '公开'}</td><td>{row.account_ids.map(id => upstreams.find(item => item.id === id)?.name).join('、') || '-'}</td><td>{row.max_concurrency}</td><td>{row.enabled ? '启用' : '停用'}</td><td><button className="text-link" onClick={() => setGroup({ id: row.id, name: row.name, max_concurrency: row.max_concurrency, account_ids: row.account_ids, member_ids: row.member_ids, is_private: row.is_private, enabled: row.enabled })}>编辑</button></td></tr>)}</tbody></table></div> : <Empty text="暂无分组" />}
    </>}

    {tab === 'models' && <>
      <div className="section-head"><h2>发布模型</h2></div>
      <form className="form-grid" onSubmit={saveMapping}>
        <label>分组<select required value={groupId} onChange={e => { setGroupId(e.target.value); setMapping({ ...mapping, upstream_account_id: '', upstream_model: '' }); setExtraRoutes([]) }}><option value="">选择分组</option>{groups.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
        <label>公开模型名<input required value={mapping.public_name} onChange={e => setMapping({ ...mapping, public_name: e.target.value })} placeholder="illustration-pro" /></label>
        <label>首选上游账户<select required value={mapping.upstream_account_id} onChange={e => { setMapping({ ...mapping, upstream_account_id: e.target.value, upstream_model: '', extra_amount: upstreams.find(row => row.id === Number(e.target.value))?.provider === 'novelai' ? '0.1' : '0' }); setExtraRoutes(rows => rows.filter(route => route.account_id !== Number(e.target.value))); if (e.target.value) fetchModels(Number(e.target.value)) }}><option value="">选择账户</option>{availableAccounts.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}</select></label>
        <label>上游模型名<input required list="primary-models" value={mapping.upstream_model} onChange={e => setMapping({ ...mapping, upstream_model: e.target.value })} placeholder="选择或手动输入" /><datalist id="primary-models">{(catalogs[Number(mapping.upstream_account_id)] || []).map(name => <option key={name} value={name} />)}</datalist></label>
        <div className="wide"><div className="section-head"><h2>备用账号映射</h2><button type="button" className="button secondary" disabled={!canAddBackup} onClick={() => setExtraRoutes(rows => [...rows, { account_id: 0, upstream_model: '' }])}><Plus size={16} />添加备用账号</button></div>{extraRoutes.map((route, index) => <div className="inline-form" key={index}><label>账号<select required value={route.account_id} onChange={e => { const id = Number(e.target.value); setExtraRoutes(rows => rows.map((item, i) => i === index ? { account_id: id, upstream_model: '' } : item)); if (id) fetchModels(id) }}><option value="0">选择账户</option>{availableAccounts.filter(a => a.id !== Number(mapping.upstream_account_id) && (a.id === route.account_id || !extraRoutes.some((item, i) => i !== index && item.account_id === a.id))).map(a => <option key={a.id} value={a.id}>{a.name}</option>)}</select></label><label className="grow">模型<input required list={`backup-models-${index}`} value={route.upstream_model} onChange={e => setExtraRoutes(rows => rows.map((item, i) => i === index ? { ...item, upstream_model: e.target.value } : item))} /><datalist id={`backup-models-${index}`}>{(catalogs[route.account_id] || []).map(name => <option key={name} value={name} />)}</datalist></label><button type="button" className="text-link" onClick={() => setExtraRoutes(rows => rows.filter((_, i) => i !== index))}>移除</button></div>)}</div>
        <label>价格 (NovelAI 为 CNY/Anlas)<input type="number" step="0.0001" min="0.0001" required value={mapping.price} onChange={e => setMapping({ ...mapping, price: e.target.value })} /></label>
        {upstreams.find(row => row.id === Number(mapping.upstream_account_id))?.provider === 'novelai' && <label>每次附加价 (CNY)<input type="number" step="0.0001" min="0" required value={mapping.extra_amount} onChange={e => setMapping({ ...mapping, extra_amount: e.target.value })} /></label>}
        <label className="check-label"><input type="checkbox" checked={mapping.enabled} onChange={e => setMapping({ ...mapping, enabled: e.target.checked })} />启用</label>
        <button className="button primary"><Plus size={16} />保存模型</button>
      </form>
      <div className="section-head"><h2>模型列表</h2></div>
      {mappings.length ? <div className="table-scroll"><table><thead><tr><th>分组</th><th>公开名称</th><th>上游路由</th><th>价格</th><th>版本</th><th>状态</th><th></th></tr></thead><tbody>{mappings.map(row => <tr key={row.id}><td>{groups.find(group => group.id === row.group_id)?.name}</td><td>{row.public_name}</td><td>{row.routes.map(route => `${upstreams.find(account => account.id === route.account_id)?.name}: ${route.upstream_model}`).join('、')}</td><td>{formatMoney(row.price || 0)} / {row.billing_mode === 'anlas' ? 'Anlas' : '次'}{row.billing_mode === 'anlas' && Number(row.extra_amount) > 0 ? ` + ${formatMoney(row.extra_amount)} / 次` : ''}</td><td>v{row.revision}</td><td>{row.enabled ? '启用' : '停用'}</td><td className="right"><button className="text-link" onClick={() => editMapping(row)}>编辑</button></td></tr>)}</tbody></table></div> : <Empty text="尚未创建模型" />}
    </>}

    {tab === 'accounts' && <>
      <div className="section-head"><h2>添加上游账户</h2></div>
      <form className="form-grid" onSubmit={createAccount}>
        <label>账户名称<input required value={account.name} onChange={e => setAccount({ ...account, name: e.target.value })} /></label>
        <label>接口类型<select value={account.provider} onChange={e => setAccount({ ...account, provider: e.target.value })}><option value="novelai">NovelAI</option><option value="openai">OpenAI 兼容</option></select></label>
        <label>API 基础地址<input required type="url" value={account.base_url} onChange={e => setAccount({ ...account, base_url: e.target.value })} placeholder="https://image.novelai.net" /></label>
        <label className="wide">上游密钥<input required type="password" autoComplete="off" value={account.api_key} onChange={e => setAccount({ ...account, api_key: e.target.value })} /></label>
        <label>最大并发数<input type="number" min="1" max="1000" required value={account.max_concurrency} onChange={e => setAccount({ ...account, max_concurrency: Number(e.target.value) })} /></label>
        {account.provider === 'novelai' && <label className="check-label"><input type="checkbox" checked={account.opus_free} onChange={e => setAccount({ ...account, opus_free: e.target.checked })} />Opus 免费条件适用</label>}
        <button className="button primary"><Plus size={16} />添加账户</button>
      </form>
      <div className="section-head"><h2>账户列表</h2></div>
      {upstreams.length ? <div className="table-scroll"><table><thead><tr><th>名称</th><th>类型</th><th>基础地址</th><th>最大并发</th><th>启用</th><th>模型</th></tr></thead><tbody>{upstreams.map(row => <tr key={row.id}><td>{row.name}</td><td>{row.provider}</td><td className="mono">{row.base_url}</td><td><input className="small-input" type="number" min="1" max="1000" defaultValue={row.max_concurrency} key={`${row.id}-${row.max_concurrency}`} onBlur={e => { const value = Number(e.target.value); if (value !== row.max_concurrency) updateAccount(row, value) }} /></td><td><input type="checkbox" checked={row.enabled} onChange={e => updateAccount(row, row.max_concurrency, e.target.checked)} /></td><td><button className="text-link" onClick={() => fetchModels(row.id)}>获取模型</button>{catalogs[row.id] && <span className="muted"> {catalogs[row.id].length} 个</span>}</td></tr>)}</tbody></table></div> : <Empty text="尚未添加上游账户" />}
    </>}

    {tab === 'users' && <UserManagement />}

    {tab === 'reconcile' && (uncertain.length ? uncertain.map(job => <div className="reconcile-row" key={job.id}>
      <div><strong className="mono">{job.id}</strong><span>{job.model} · <Status value={job.status} /></span><p>{job.error}</p></div>
      <input placeholder="成功时填写图片 URL" value={resolution[job.id] || ''} onChange={e => setResolution({ ...resolution, [job.id]: e.target.value })} />
      {job.anlas_cost !== null && <input type="number" min="0" placeholder="实际消耗 Anlas" value={resolutionAnlas[job.id] || ''} onChange={e => setResolutionAnlas({ ...resolutionAnlas, [job.id]: e.target.value })} />}
      <div className="button-group"><button className="button secondary" onClick={() => submit(`/api/admin/uncertain/${job.id}/resolve`, { succeeded: false, note: '人工核对：未产生有效结果' })}>释放预留</button><button className="button primary" onClick={() => submit(`/api/admin/uncertain/${job.id}/resolve`, { succeeded: true, image_url: resolution[job.id], anlas_charged: job.anlas_cost !== null && resolutionAnlas[job.id] !== undefined ? Number(resolutionAnlas[job.id]) : null })}>确认成功</button></div>
    </div>) : <Empty text="没有待核对任务" />)}
  </div>
}
