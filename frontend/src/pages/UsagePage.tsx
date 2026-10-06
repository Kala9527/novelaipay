import { useEffect, useState } from 'react'
import { RefreshCw, Trash2, ChevronLeft, ChevronRight, Download, X } from 'lucide-react'
import { api, downloadCsv, formatDate, formatMoney, post } from '../lib/api'
import type { AdminUser, Job } from '../types'
import { Empty, Notice, PageHeader, Status } from '../components/UI'

type UsageJob = Job & { user_id: number; user_name: string }
type UsageResponse = { total: number; items: UsageJob[] }

export function UsagePage({ isAdmin }: { isAdmin: boolean }) {
  const [rows, setRows] = useState<UsageJob[]>([])
  const [total, setTotal] = useState(0)
  const [users, setUsers] = useState<AdminUser[]>([])
  const [models, setModels] = useState<string[]>([])
  const [userId, setUserId] = useState('')
  const [status, setStatus] = useState('')
  const [model, setModel] = useState('')
  const [search, setSearch] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [page, setPage] = useState(0)
  const [selected, setSelected] = useState<UsageJob | null>(null)
  const [checked, setChecked] = useState<string[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const limit = 50

  async function load() {
    try {
      const query = new URLSearchParams({ offset: String(page * limit), limit: String(limit) })
      if (isAdmin && userId) query.set('user_id', userId)
      if (status) query.set('status', status)
      if (model) query.set('model', model)
      if (search.trim()) query.set('search', search.trim())
      if (dateFrom) query.set('date_from', dateFrom)
      if (dateTo) query.set('date_to', dateTo)
      const result = await api<UsageResponse>(`/api/usage?${query}`)
      setRows(result.items)
      setTotal(result.total)
      setChecked([])
      setSelected(current => result.items.find(row => row.id === current?.id) || null)
      setError('')
    } catch (e) { setError((e as Error).message) }
  }
  useEffect(() => { load() }, [page, userId, status, model, search, dateFrom, dateTo, isAdmin])
  useEffect(() => {
    api<string[]>('/api/usage/models').then(setModels).catch(e => setError(e.message))
    if (isAdmin) api<AdminUser[]>('/api/admin/users?include_deleted=true').then(setUsers).catch(e => setError(e.message))
  }, [isAdmin])

  async function remove(ids: string[]) {
    if (!ids.length || !window.confirm(`删除 ${ids.length} 条使用记录？此操作不可恢复。`)) return
    setBusy(true)
    try {
      await post('/api/usage/delete', { ids })
      if (page > 0 && rows.length === ids.length) setPage(page - 1)
      else await load()
    } catch (e) { setError((e as Error).message) }
    finally { setBusy(false) }
  }
  async function exportRows(ids?: string[]) {
    const query = new URLSearchParams()
    if (isAdmin && userId) query.set('user_id', userId)
    if (status) query.set('status', status)
    if (model) query.set('model', model)
    if (search.trim()) query.set('search', search.trim())
    if (dateFrom) query.set('date_from', dateFrom)
    if (dateTo) query.set('date_to', dateTo)
    ids?.forEach(id => query.append('ids', id))
    try { await downloadCsv(`/api/usage/export?${query}`, 'usage-records.csv') }
    catch (e) { setError((e as Error).message) }
  }
  const allChecked = rows.length > 0 && rows.every(row => checked.includes(row.id))
  return <div className="page">
    <PageHeader title="使用记录" action={<div className="button-group"><button className="button secondary" onClick={() => exportRows()}><Download size={16} />导出筛选结果</button><button className="icon-button" title="刷新" aria-label="刷新" onClick={load}><RefreshCw size={17} /></button></div>} />
    <div className="usage-filters">
      {isAdmin && <label>使用用户<select value={userId} onChange={e => { setPage(0); setUserId(e.target.value) }}><option value="">所有用户</option>{users.map(user => <option key={user.id} value={user.id}>{user.name || user.email}</option>)}</select></label>}
      <label>状态<select value={status} onChange={e => { setPage(0); setStatus(e.target.value) }}><option value="">全部状态</option><option value="queued">排队中</option><option value="running">生成中</option><option value="succeeded">成功</option><option value="failed">失败</option><option value="uncertain">待核对</option></select></label>
      <label>模型<select value={model} onChange={e => { setPage(0); setModel(e.target.value) }}><option value="">全部模型</option>{models.map(item => <option key={item} value={item}>{item}</option>)}</select></label>
      <label>任务 ID<input value={search} onChange={e => { setPage(0); setSearch(e.target.value) }} placeholder="搜索任务 ID" /></label>
      <label>开始日期 (北京时间)<input type="date" value={dateFrom} onChange={e => { setPage(0); setDateFrom(e.target.value) }} /></label>
      <label>结束日期 (北京时间)<input type="date" value={dateTo} onChange={e => { setPage(0); setDateTo(e.target.value) }} /></label>
    </div>
    {error && <Notice text={error} error />}
    {isAdmin && checked.length > 0 && <div className="usage-actions"><span>已选择 {checked.length} 条</span><button className="button secondary" onClick={() => exportRows(checked)}><Download size={15} />导出选中</button><button className="button secondary danger-text" disabled={busy} onClick={() => remove(checked)}><Trash2 size={15} />批量删除</button></div>}
    {rows.length ? <div className="table-scroll"><table><thead><tr>{isAdmin && <th><input type="checkbox" aria-label="选择本页" checked={allChecked} onChange={e => setChecked(e.target.checked ? rows.map(row => row.id) : [])} /></th>}<th>任务 ID</th><th>使用用户</th><th>模型</th><th>状态</th><th>费用</th><th>提交时间</th>{isAdmin && <th>操作</th>}</tr></thead><tbody>{rows.map(row => <tr key={row.id} className="clickable" onClick={() => setSelected(row)}>{isAdmin && <td onClick={e => e.stopPropagation()}><input type="checkbox" aria-label={`选择 ${row.id}`} checked={checked.includes(row.id)} onChange={e => setChecked(current => e.target.checked ? [...current, row.id] : current.filter(id => id !== row.id))} /></td>}<td className="mono">{row.id.slice(0, 12)}</td><td>{row.user_name}</td><td>{row.model}</td><td><Status value={row.status} /></td><td>{formatMoney(row.amount)}</td><td>{formatDate(row.created_at)}</td>{isAdmin && <td onClick={e => e.stopPropagation()}><button className="icon-button danger" title="删除记录" disabled={busy || ['queued', 'running', 'uncertain'].includes(row.status)} onClick={() => remove([row.id])}><Trash2 size={16} /></button></td>}</tr>)}</tbody></table></div> : <Empty text="暂无使用记录" />}
    <div className="usage-pagination"><span>共 {total} 条</span><button className="icon-button" title="上一页" disabled={page === 0} onClick={() => setPage(page - 1)}><ChevronLeft size={18} /></button><span>第 {page + 1} 页</span><button className="icon-button" title="下一页" disabled={(page + 1) * limit >= total} onClick={() => setPage(page + 1)}><ChevronRight size={18} /></button></div>
    {selected && <div className="detail-panel"><div className="section-head"><h2>记录详情</h2><button className="icon-button" title="关闭详情" onClick={() => setSelected(null)}><X size={18} /></button></div><dl className="detail-grid"><dt>任务 ID</dt><dd className="mono">{selected.id}</dd><dt>使用用户</dt><dd>{selected.user_name}</dd><dt>模型</dt><dd>{selected.model}</dd><dt>尺寸</dt><dd>{selected.size}</dd><dt>状态</dt><dd><Status value={selected.status} /></dd><dt>Anlas</dt><dd>{selected.anlas_cost ?? '-'}</dd><dt>提示词</dt><dd>{selected.prompt}</dd>{selected.error && <><dt>说明</dt><dd>{selected.error}</dd></>}</dl></div>}
  </div>
}
