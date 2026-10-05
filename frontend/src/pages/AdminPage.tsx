import { useEffect, useState, type FormEvent } from 'react'
import { Check, Pencil, Plus, RefreshCw, RotateCcw, Search, Trash2, X } from 'lucide-react'
import { api, formatDate, formatMoney, post } from '../lib/api'
import type { Group, GroupRecipient, Job, Mapping, Upstream } from '../types'
import { Empty, Notice, PageHeader, Status } from '../components/UI'
import { UserManagement } from '../components/UserManagement'

type Tab = 'models' | 'groups' | 'accounts' | 'users' | 'reconcile'
const emptyGroup = () => ({ id: null as number | null, name: '', max_concurrency: 10, account_ids: [] as number[], member_ids: [] as number[], is_private: false, enabled: true })
const emptyAccount = () => ({ id: null as number | null, name: '', base_url: 'https://image.novelai.net', api_key: '', provider: 'novelai', opus_free: false, max_concurrency: 10, enabled: true })
const emptyMapping = () => ({ id: null as number | null, public_name: '', upstream_account_id: '', upstream_model: '', price: '', extra_amount: '0.1', enabled: true })

export function AdminPage() {
  const [tab, setTab] = useState<Tab>('models')
  const [editor, setEditor] = useState<Tab | null>(null)
  const [showArchived, setShowArchived] = useState(false)
  const [search, setSearch] = useState('')
  const [upstreams, setUpstreams] = useState<Upstream[]>([])
  const [groups, setGroups] = useState<Group[]>([])
  const [catalogs, setCatalogs] = useState<Record<number, string[]>>({})
  const [group, setGroup] = useState(emptyGroup)
  const [recipients, setRecipients] = useState<GroupRecipient[]>([])
  const [groupId, setGroupId] = useState('')
  const [extraRoutes, setExtraRoutes] = useState<{ account_id: number; upstream_model: string }[]>([])
  const [mappings, setMappings] = useState<Mapping[]>([])
  const [uncertain, setUncertain] = useState<Job[]>([])
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [account, setAccount] = useState(emptyAccount)
  const [mapping, setMapping] = useState(emptyMapping)
  const [resolution, setResolution] = useState<Record<string, string>>({})
  const [resolutionAnlas, setResolutionAnlas] = useState<Record<string, string>>({})
  const [resolutionNote, setResolutionNote] = useState<Record<string, string>>({})
  const [editingUncertainId, setEditingUncertainId] = useState<string | null>(null)

  function load() {
    api<Upstream[]>('/api/admin/upstreams?include_deleted=true').then(setUpstreams).catch(e => setError(e.message))
    api<Group[]>('/api/admin/groups?include_deleted=true').then(setGroups).catch(e => setError(e.message))
    api<GroupRecipient[]>('/api/admin/group-recipients').then(setRecipients).catch(e => setError(e.message))
    api<Mapping[]>('/api/admin/mappings?include_deleted=true').then(setMappings).catch(e => setError(e.message))
    api<Job[]>('/api/admin/uncertain').then(setUncertain).catch(e => setError(e.message))
  }
  useEffect(() => { load() }, [])

  async function submit(path: string, data: unknown, done?: () => void) {
    setError(''); setMessage('')
    try { await post(path, data); setMessage('操作成功'); done?.(); load() }
    catch (e) { setError((e as Error).message) }
  }
  async function remove(path: string, label: string, warning: string) {
    if (!window.confirm(`删除 ${label}？${warning}`)) return
    setError(''); setMessage('')
    try { await api(path, { method: 'DELETE' }); setMessage(`${label}已删除`); setEditor(null); load() }
    catch (e) { setError((e as Error).message) }
  }
  function restore(path: string, label: string) {
    submit(path, {}, () => setMessage(`${label}已恢复，请检查配置后启用`))
  }
  function openEditor(next: Tab) {
    setEditor(next)
    requestAnimationFrame(() => document.getElementById('admin-editor')?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
  }

  async function fetchModels(id: number) {
    try { const result = await api<{ models: string[] }>(`/api/admin/upstreams/${id}/models`); setCatalogs(current => ({ ...current, [id]: result.models })) }
    catch (e) { setError((e as Error).message) }
  }

  async function saveAccount(event: FormEvent) {
    event.preventDefault(); setError(''); setMessage('')
    try {
      if (account.id) await api(`/api/admin/upstreams/${account.id}`, { method: 'PATCH', body: JSON.stringify({ ...account, api_key: account.api_key || undefined }) })
      else await post<Upstream>('/api/admin/upstreams', account)
      setAccount(emptyAccount()); setEditor(null)
      setMessage(account.id ? '账户已更新' : '账户已添加')
      load()
    } catch (e) { setError((e as Error).message) }
  }

  function saveMapping(event: FormEvent) {
    event.preventDefault()
    const provider = upstreams.find(row => row.id === Number(mapping.upstream_account_id))?.provider
    submit('/api/admin/mappings', { ...mapping, group_id: Number(groupId), routes: [{ account_id: Number(mapping.upstream_account_id), upstream_model: mapping.upstream_model }, ...extraRoutes], extra_amount: provider === 'novelai' ? mapping.extra_amount : '0', upstream_account_id: Number(mapping.upstream_account_id) },
      () => { setMapping(emptyMapping()); setExtraRoutes([]); setGroupId(''); setEditor(null) })
  }

  function editMapping(row: Mapping) {
    setGroupId(String(row.group_id))
    setExtraRoutes(row.routes.slice(1))
    setMapping({ public_name: row.public_name, upstream_account_id: String(row.upstream_account_id), upstream_model: row.upstream_model,
      price: row.price || '', extra_amount: row.extra_amount || '0', id: row.id, enabled: row.enabled })
    openEditor('models')
  }
  function editGroup(row: Group) {
    setGroup({ id: row.id, name: row.name, max_concurrency: row.max_concurrency,
      account_ids: [...row.account_ids], member_ids: [...row.member_ids],
      is_private: row.is_private, enabled: row.enabled })
    openEditor('groups')
  }
  function editAccount(row: Upstream) {
    setAccount({ id: row.id, name: row.name, base_url: row.base_url, api_key: '',
      provider: row.provider, opus_free: row.opus_free, max_concurrency: row.max_concurrency,
      enabled: row.enabled })
    openEditor('accounts')
  }

  const activeGroups = groups.filter(row => !row.deleted_at)
  const activeAccounts = upstreams.filter(row => !row.deleted_at)
  const selectedGroup = activeGroups.find(row => row.id === Number(groupId))
  const availableAccounts = activeAccounts.filter(row => selectedGroup?.account_ids.includes(row.id))
  const canAddBackup = !!mapping.upstream_account_id && extraRoutes.length < availableAccounts.length - 1
  const query = search.trim().toLocaleLowerCase()
  const visibleGroups = groups.filter(row => (showArchived || !row.deleted_at) && row.name.toLocaleLowerCase().includes(query))
  const visibleAccounts = upstreams.filter(row => (showArchived || !row.deleted_at) && `${row.name} ${row.base_url} ${row.provider}`.toLocaleLowerCase().includes(query))
  const visibleMappings = mappings.filter(row => (showArchived || !row.deleted_at) && `${row.public_name} ${groups.find(group => group.id === row.group_id)?.name || ''}`.toLocaleLowerCase().includes(query))
  const toolbar = (title: string, count: number, create: () => void, createLabel: string) => <div className="admin-toolbar"><div><h2>{title}</h2><span>{count} 项</span></div><div className="admin-toolbar-actions"><label className="admin-search"><Search size={15} /><input aria-label={`搜索${title}`} placeholder="搜索" value={search} onChange={e => setSearch(e.target.value)} /></label><label className="check-label"><input type="checkbox" checked={showArchived} onChange={e => setShowArchived(e.target.checked)} />显示已删除</label><button className="button primary" type="button" onClick={create}><Plus size={16} />{createLabel}</button></div></div>

  return <div className="page admin-page">
    <PageHeader title="管理设置" subtitle="配置分组、上游和模型定价" action={<button className="button secondary" onClick={load}><RefreshCw size={16} />刷新</button>} />
    <div className="tabs">{([['models', '模型与定价'], ['groups', '分组'], ['accounts', '上游账户'], ['users', '用户与余额'], ['reconcile', `待核对 (${uncertain.length})`]] as [Tab, string][]).map(([key, label]) => <button key={key} className={tab === key ? 'tab active' : 'tab'} onClick={() => { setTab(key); setEditor(null); setSearch(''); setError(''); setMessage('') }}>{label}</button>)}</div>
    {error && <Notice text={error} error />}{message && <Notice text={message} />}

    {tab === 'groups' && <>
      {toolbar('分组列表', visibleGroups.length, () => { setGroup(emptyGroup()); openEditor('groups') }, '创建分组')}
      {editor === 'groups' && <section id="admin-editor" className="admin-edit-section"><div className="admin-edit-heading"><h3>{group.id ? `编辑分组 · ${group.name}` : '创建分组'}</h3><button type="button" className="icon-button" title="关闭编辑" onClick={() => setEditor(null)}><X size={17} /></button></div>
      <form className="form-grid" onSubmit={e => { e.preventDefault(); submit('/api/admin/groups', group, () => { setGroup(emptyGroup()); setEditor(null) }) }}>
        <label>分组名称<input required value={group.name} onChange={e => setGroup({ ...group, name: e.target.value })} /></label>
        <label>最大并发数<input type="number" min="1" max="1000" required value={group.max_concurrency} onChange={e => setGroup({ ...group, max_concurrency: Number(e.target.value) })} /></label>
        <div className="wide"><strong>上游账号</strong><div className="admin-choice-grid">{activeAccounts.map(row => <label className="check-label" key={row.id}><input type="checkbox" checked={group.account_ids.includes(row.id)} onChange={e => setGroup(current => ({ ...current, account_ids: e.target.checked ? [...current.account_ids, row.id] : current.account_ids.filter(id => id !== row.id) }))} />{row.name}</label>)}</div></div>
        <label>可见范围<select value={group.is_private ? 'private' : 'public'} onChange={e => setGroup({ ...group, is_private: e.target.value === 'private', member_ids: [] })}><option value="public">公开</option><option value="private">专属</option></select></label>
        {group.is_private && <div className="wide"><strong>授权用户</strong><div className="admin-choice-grid">{recipients.map(row => <label className="check-label" key={row.id}><input type="checkbox" checked={group.member_ids.includes(row.id)} onChange={e => setGroup(current => ({ ...current, member_ids: e.target.checked ? [...current.member_ids, row.id] : current.member_ids.filter(id => id !== row.id) }))} />{row.name || row.email}{row.is_admin ? '（管理员）' : ''}</label>)}</div></div>}
        <label className="check-label"><input type="checkbox" checked={group.enabled} onChange={e => setGroup({ ...group, enabled: e.target.checked })} />启用</label>
        <div className="admin-form-actions"><button className="button primary" disabled={group.is_private && !group.member_ids.length}><Check size={16} />保存分组</button><button type="button" className="button secondary" onClick={() => setEditor(null)}>取消</button></div>
      </form></section>}
      {visibleGroups.length ? <div className="table-scroll admin-table"><table><thead><tr><th>分组</th><th>范围</th><th>上游账号</th><th>最大并发</th><th>状态</th><th className="right">操作</th></tr></thead><tbody>{visibleGroups.map(row => <tr key={row.id}><td><strong>{row.name}</strong></td><td>{row.is_private ? `专属 · ${row.member_ids.length} 人` : '公开'}</td><td>{row.account_ids.map(id => upstreams.find(item => item.id === id)?.name).filter(Boolean).join('、') || '-'}</td><td>{row.max_concurrency}</td><td><span className={`admin-state ${row.deleted_at ? 'archived' : row.enabled ? 'active' : ''}`}>{row.deleted_at ? '已删除' : row.enabled ? '启用' : '停用'}</span></td><td className="right"><div className="admin-row-actions">{row.deleted_at ? <button className="icon-button" title="恢复分组" onClick={() => restore(`/api/admin/groups/${row.id}/restore`, row.name)}><RotateCcw size={16} /></button> : <><button className="icon-button" title="编辑分组" onClick={() => editGroup(row)}><Pencil size={16} /></button><button className="icon-button danger" title="删除分组" onClick={() => remove(`/api/admin/groups/${row.id}`, row.name, '组内密钥将被撤销，历史任务会保留。')}><Trash2 size={16} /></button></>}</div></td></tr>)}</tbody></table></div> : <Empty text="暂无分组" />}
    </>}

    {tab === 'models' && <>
      {toolbar('模型列表', visibleMappings.length, () => { setMapping(emptyMapping()); setGroupId(''); setExtraRoutes([]); openEditor('models') }, '发布模型')}
      {editor === 'models' && <section id="admin-editor" className="admin-edit-section"><div className="admin-edit-heading"><h3>{mapping.id ? `编辑模型 · ${mapping.public_name}` : '发布模型'}</h3><button type="button" className="icon-button" title="关闭编辑" onClick={() => setEditor(null)}><X size={17} /></button></div>
      <form className="form-grid" onSubmit={saveMapping}>
        <label>分组<select required value={groupId} onChange={e => { setGroupId(e.target.value); setMapping({ ...mapping, upstream_account_id: '', upstream_model: '' }); setExtraRoutes([]) }}><option value="">选择分组</option>{activeGroups.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
        <label>公开模型名<input required value={mapping.public_name} onChange={e => setMapping({ ...mapping, public_name: e.target.value })} placeholder="illustration-pro" /></label>
        <label>首选上游账户<select required value={mapping.upstream_account_id} onChange={e => { setMapping({ ...mapping, upstream_account_id: e.target.value, upstream_model: '', extra_amount: upstreams.find(row => row.id === Number(e.target.value))?.provider === 'novelai' ? '0.1' : '0' }); setExtraRoutes(rows => rows.filter(route => route.account_id !== Number(e.target.value))); if (e.target.value) fetchModels(Number(e.target.value)) }}><option value="">选择账户</option>{availableAccounts.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}</select></label>
        <label>上游模型名<input required list="primary-models" value={mapping.upstream_model} onChange={e => setMapping({ ...mapping, upstream_model: e.target.value })} placeholder="选择或手动输入" /><datalist id="primary-models">{(catalogs[Number(mapping.upstream_account_id)] || []).map(name => <option key={name} value={name} />)}</datalist></label>
        <div className="wide"><div className="section-head"><h2>备用账号映射</h2><button type="button" className="button secondary" disabled={!canAddBackup} onClick={() => setExtraRoutes(rows => [...rows, { account_id: 0, upstream_model: '' }])}><Plus size={16} />添加备用账号</button></div>{extraRoutes.map((route, index) => <div className="inline-form" key={index}><label>账号<select required value={route.account_id} onChange={e => { const id = Number(e.target.value); setExtraRoutes(rows => rows.map((item, i) => i === index ? { account_id: id, upstream_model: '' } : item)); if (id) fetchModels(id) }}><option value="0">选择账户</option>{availableAccounts.filter(a => a.id !== Number(mapping.upstream_account_id) && (a.id === route.account_id || !extraRoutes.some((item, i) => i !== index && item.account_id === a.id))).map(a => <option key={a.id} value={a.id}>{a.name}</option>)}</select></label><label className="grow">模型<input required list={`backup-models-${index}`} value={route.upstream_model} onChange={e => setExtraRoutes(rows => rows.map((item, i) => i === index ? { ...item, upstream_model: e.target.value } : item))} /><datalist id={`backup-models-${index}`}>{(catalogs[route.account_id] || []).map(name => <option key={name} value={name} />)}</datalist></label><button type="button" className="text-link" onClick={() => setExtraRoutes(rows => rows.filter((_, i) => i !== index))}>移除</button></div>)}</div>
        <label>价格 (NovelAI 为 CNY/Anlas)<input type="number" step="0.0001" min="0.0001" required value={mapping.price} onChange={e => setMapping({ ...mapping, price: e.target.value })} /></label>
        {upstreams.find(row => row.id === Number(mapping.upstream_account_id))?.provider === 'novelai' && <label>每次附加价 (CNY)<input type="number" step="0.0001" min="0" required value={mapping.extra_amount} onChange={e => setMapping({ ...mapping, extra_amount: e.target.value })} /></label>}
        <label className="check-label"><input type="checkbox" checked={mapping.enabled} onChange={e => setMapping({ ...mapping, enabled: e.target.checked })} />启用</label>
        <div className="admin-form-actions"><button className="button primary"><Check size={16} />保存模型</button><button type="button" className="button secondary" onClick={() => setEditor(null)}>取消</button></div>
      </form></section>}
      {visibleMappings.length ? <div className="table-scroll admin-table"><table><thead><tr><th>模型 / 分组</th><th>上游路由</th><th>价格</th><th>版本</th><th>状态</th><th className="right">操作</th></tr></thead><tbody>{visibleMappings.map(row => <tr key={row.id}><td><strong>{row.public_name}</strong><small>{groups.find(group => group.id === row.group_id)?.name || '-'}</small></td><td>{row.routes.map(route => `${upstreams.find(account => account.id === route.account_id)?.name || '-'}: ${route.upstream_model}`).join('、')}</td><td>{formatMoney(row.price || 0)} / {row.billing_mode === 'anlas' ? 'Anlas' : '次'}{row.billing_mode === 'anlas' && Number(row.extra_amount) > 0 ? <small>+ {formatMoney(row.extra_amount)} / 次</small> : null}</td><td>v{row.revision}</td><td><span className={`admin-state ${row.deleted_at ? 'archived' : row.enabled ? 'active' : ''}`}>{row.deleted_at ? '已删除' : row.enabled ? '启用' : '停用'}</span></td><td className="right"><div className="admin-row-actions">{row.deleted_at ? <button className="icon-button" title="恢复模型" onClick={() => restore(`/api/admin/mappings/${row.id}/restore`, row.public_name)}><RotateCcw size={16} /></button> : <><button className="icon-button" title="编辑模型" onClick={() => editMapping(row)}><Pencil size={16} /></button><button className="icon-button danger" title="删除模型" onClick={() => remove(`/api/admin/mappings/${row.id}`, row.public_name, '历史账单会保留。')}><Trash2 size={16} /></button></>}</div></td></tr>)}</tbody></table></div> : <Empty text="暂无模型" />}
    </>}

    {tab === 'accounts' && <>
      {toolbar('上游账户', visibleAccounts.length, () => { setAccount(emptyAccount()); openEditor('accounts') }, '添加账户')}
      {editor === 'accounts' && <section id="admin-editor" className="admin-edit-section"><div className="admin-edit-heading"><h3>{account.id ? `编辑账户 · ${account.name}` : '添加上游账户'}</h3><button type="button" className="icon-button" title="关闭编辑" onClick={() => setEditor(null)}><X size={17} /></button></div>
      <form className="form-grid" onSubmit={saveAccount}>
        <label>账户名称<input required value={account.name} onChange={e => setAccount({ ...account, name: e.target.value })} /></label>
        <label>接口类型<select disabled={!!account.id} value={account.provider} onChange={e => setAccount({ ...account, provider: e.target.value })}><option value="novelai">NovelAI</option><option value="openai">OpenAI 兼容</option></select></label>
        <label>API 基础地址<input required type="url" value={account.base_url} onChange={e => setAccount({ ...account, base_url: e.target.value })} placeholder="https://image.novelai.net" /></label>
        <label className="wide">上游密钥<input required={!account.id} type="password" autoComplete="new-password" value={account.api_key} onChange={e => setAccount({ ...account, api_key: e.target.value })} placeholder={account.id ? '留空则不修改' : ''} /></label>
        <label>最大并发数<input type="number" min="1" max="1000" required value={account.max_concurrency} onChange={e => setAccount({ ...account, max_concurrency: Number(e.target.value) })} /></label>
        {account.provider === 'novelai' && <label className="check-label"><input type="checkbox" checked={account.opus_free} onChange={e => setAccount({ ...account, opus_free: e.target.checked })} />Opus 免费条件适用</label>}
        <label className="check-label"><input type="checkbox" checked={account.enabled} onChange={e => setAccount({ ...account, enabled: e.target.checked })} />启用</label>
        <div className="admin-form-actions"><button className="button primary"><Check size={16} />保存账户</button><button type="button" className="button secondary" onClick={() => setEditor(null)}>取消</button></div>
      </form></section>}
      {visibleAccounts.length ? <div className="table-scroll admin-table"><table><thead><tr><th>账户</th><th>类型</th><th>基础地址</th><th>最大并发</th><th>状态</th><th className="right">操作</th></tr></thead><tbody>{visibleAccounts.map(row => <tr key={row.id}><td><strong>{row.name}</strong></td><td>{row.provider}</td><td className="mono">{row.base_url}</td><td>{row.max_concurrency}</td><td><span className={`admin-state ${row.deleted_at ? 'archived' : row.enabled ? 'active' : ''}`}>{row.deleted_at ? '已删除' : row.enabled ? '启用' : '停用'}</span></td><td className="right"><div className="admin-row-actions">{row.deleted_at ? <button className="icon-button" title="恢复账户" onClick={() => restore(`/api/admin/upstreams/${row.id}/restore`, row.name)}><RotateCcw size={16} /></button> : <><button className="icon-button" title="获取模型" onClick={() => fetchModels(row.id)}><RefreshCw size={16} /></button><button className="icon-button" title="编辑账户" onClick={() => editAccount(row)}><Pencil size={16} /></button><button className="icon-button danger" title="删除账户" onClick={() => remove(`/api/admin/upstreams/${row.id}`, row.name, '请先从已发布模型中移除该账户。')}><Trash2 size={16} /></button></>}</div></td></tr>)}</tbody></table></div> : <Empty text="暂无上游账户" />}
      {Object.keys(catalogs).length > 0 && <div className="admin-catalog-count">已获取模型：{Object.entries(catalogs).map(([id, names]) => `${upstreams.find(row => row.id === Number(id))?.name || id} ${names.length} 个`).join(' · ')}</div>}
    </>}

    {tab === 'users' && <UserManagement />}

    {tab === 'reconcile' && <>
      <div className="admin-toolbar"><div><h2>待核对任务</h2><span>{uncertain.length} 项</span></div></div>
      {uncertain.length ? <div className="admin-reconcile-list">{uncertain.map(job => <section className="admin-reconcile-row" key={job.id}>
        <div className="admin-reconcile-summary"><div><strong className="mono">{job.id}</strong><span>{job.model} · {formatDate(job.created_at)}</span></div><div className="admin-row-actions"><Status value={job.status} /><button className="icon-button" title="编辑核对" onClick={() => setEditingUncertainId(current => current === job.id ? null : job.id)}><Pencil size={16} /></button><button className="icon-button danger" title="删除待核对任务" onClick={() => remove(`/api/admin/uncertain/${job.id}`, `任务 ${job.id}`, '预留金额将释放，任务会标记失败并从记录中隐藏；请先确认上游没有实际扣费。')}><Trash2 size={16} /></button></div></div>
        {job.error && <p className="admin-reconcile-error">{job.error}</p>}
        {editingUncertainId === job.id && <><div className="admin-reconcile-fields"><label>结果图片 URL<input type="url" placeholder="确认成功时填写" value={resolution[job.id] || ''} onChange={e => setResolution({ ...resolution, [job.id]: e.target.value })} /></label>
          {job.anlas_cost !== null && <label>实际消耗 Anlas<input type="number" min="0" placeholder="填写实际消耗" value={resolutionAnlas[job.id] || ''} onChange={e => setResolutionAnlas({ ...resolutionAnlas, [job.id]: e.target.value })} /></label>}
          <label>处理备注<input value={resolutionNote[job.id] || ''} maxLength={500} onChange={e => setResolutionNote({ ...resolutionNote, [job.id]: e.target.value })} /></label></div>
        <div className="admin-reconcile-actions"><button className="button secondary" onClick={() => submit(`/api/admin/uncertain/${job.id}/resolve`, { succeeded: false, note: resolutionNote[job.id] || '人工核对：未产生有效结果' }, () => setEditingUncertainId(null))}>释放预留</button><button className="button primary" disabled={!resolution[job.id] || (job.anlas_cost !== null && resolutionAnlas[job.id] === undefined)} onClick={() => submit(`/api/admin/uncertain/${job.id}/resolve`, { succeeded: true, image_url: resolution[job.id], anlas_charged: job.anlas_cost !== null ? Number(resolutionAnlas[job.id]) : null, note: resolutionNote[job.id] || null }, () => setEditingUncertainId(null))}><Check size={15} />确认成功</button></div></>}
      </section>)}</div> : <Empty text="没有待核对任务" />}
    </>}
  </div>
}
