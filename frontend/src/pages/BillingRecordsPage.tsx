import { useEffect, useState } from 'react'
import { Trash2 } from 'lucide-react'
import { api, formatDate, formatMoney, post } from '../lib/api'
import type { AdminUser, Billing } from '../types'
import { Empty, Notice, PageHeader } from '../components/UI'

export function BillingRecordsPage({ isAdmin }: { isAdmin: boolean }) {
  const [data, setData] = useState<Billing | null>(null)
  const [users, setUsers] = useState<AdminUser[]>([])
  const [models, setModels] = useState<string[]>([])
  const [filters, setFilters] = useState({ user_id: '', kind: '', model: '', search: '', date_from: '', date_to: '' })
  const [page, setPage] = useState(0)
  const [checkedLedger, setCheckedLedger] = useState<number[]>([])
  const [checkedUsage, setCheckedUsage] = useState<number[]>([])
  const [error, setError] = useState('')
  const limit = 50
  function load() {
    const query = new URLSearchParams({ offset: String(page * limit), limit: String(limit) })
    Object.entries(filters).forEach(([key, value]) => { if (value) query.set(key, value) })
    api<Billing>(`/api/billing?${query}`).then(rows => { setData(rows); setCheckedLedger([]); setCheckedUsage([]); setError('') }).catch(e => setError(e.message))
  }
  useEffect(() => { load() }, [page, filters])
  useEffect(() => {
    api<string[]>('/api/usage/models').then(setModels).catch(e => setError(e.message))
    if (isAdmin) api<AdminUser[]>('/api/admin/users?include_deleted=true').then(setUsers).catch(e => setError(e.message))
  }, [isAdmin])
  function change(key: keyof typeof filters, value: string) { setPage(0); setFilters(current => ({ ...current, [key]: value })) }
  async function remove(ledger_ids: number[], usage_ids: number[]) {
    if (!window.confirm(`删除 ${ledger_ids.length + usage_ids.length} 条展示记录？`)) return
    try { await post('/api/billing/delete', { ledger_ids, usage_ids }); load() }
    catch (e) { setError((e as Error).message) }
  }
  return <div className="page">
    <PageHeader title="账单流水" />
    {filters.user_id !== '0' && <div className="balance-band"><div><span>账户余额</span><strong>{formatMoney(data?.balance || '0')}</strong></div><div><span>任务预留</span><strong>{formatMoney(data?.reserved || '0')}</strong></div><div><span>可用余额</span><strong>{formatMoney(Number(data?.balance || 0) - Number(data?.reserved || 0))}</strong></div></div>}
    <div className="usage-filters">
      {isAdmin && <label>用户<select value={filters.user_id} onChange={e => change('user_id', e.target.value)}><option value="">我的账户</option><option value="0">全部用户</option>{users.map(user => <option key={user.id} value={user.id}>{user.name || user.email}</option>)}</select></label>}
      <label>流水类型<select value={filters.kind} onChange={e => change('kind', e.target.value)}><option value="">全部类型</option><option value="usage">生图消费</option><option value="payment">支付充值</option><option value="admin_credit">管理员入账</option></select></label>
      <label>消费模型<select value={filters.model} onChange={e => change('model', e.target.value)}><option value="">全部模型</option>{models.map(model => <option key={model} value={model}>{model}</option>)}</select></label>
      <label>关联 ID<input value={filters.search} onChange={e => change('search', e.target.value)} placeholder="任务或流水 ID" /></label>
      <label>开始日期 (北京时间)<input type="date" value={filters.date_from} onChange={e => change('date_from', e.target.value)} /></label>
      <label>结束日期 (北京时间)<input type="date" value={filters.date_to} onChange={e => change('date_to', e.target.value)} /></label>
    </div>
    {error && <Notice text={error} error />}
    <div className="section-head"><h2>资金流水 ({data?.ledger_total || 0})</h2>{isAdmin && checkedLedger.length > 0 && <button className="button secondary danger-text" onClick={() => remove(checkedLedger, [])}><Trash2 size={15} />批量删除</button>}</div>
    {data?.ledger.length ? <div className="table-scroll"><table><thead><tr>{isAdmin && <th><input type="checkbox" aria-label="选择本页流水" checked={data.ledger.every(row => checkedLedger.includes(row.id))} onChange={e => setCheckedLedger(e.target.checked ? data.ledger.map(row => row.id) : [])} /></th>}<th>用户</th><th>类型</th><th>关联记录</th><th>时间</th><th className="right">金额</th>{isAdmin && <th>操作</th>}</tr></thead><tbody>{data.ledger.map(row => <tr key={row.id}>{isAdmin && <td><input type="checkbox" aria-label={`选择流水 ${row.id}`} checked={checkedLedger.includes(row.id)} onChange={e => setCheckedLedger(current => e.target.checked ? [...current, row.id] : current.filter(id => id !== row.id))} /></td>}<td>{row.user_name}</td><td>{row.kind === 'usage' ? '生图消费' : row.kind === 'payment' ? '支付充值' : '管理员入账'}</td><td className="mono">{row.reference}</td><td>{formatDate(row.created_at)}</td><td className={`right money ${Number(row.amount) > 0 ? 'positive' : ''}`}>{Number(row.amount) > 0 ? '+' : ''}{formatMoney(row.amount)}</td>{isAdmin && <td><button className="icon-button danger" title="删除流水" onClick={() => remove([row.id], [])}><Trash2 size={16} /></button></td>}</tr>)}</tbody></table></div> : <Empty text="暂无资金流水" />}
    <div className="section-head"><h2>消费记录 ({data?.usage_total || 0})</h2>{isAdmin && checkedUsage.length > 0 && <button className="button secondary danger-text" onClick={() => remove([], checkedUsage)}><Trash2 size={15} />批量删除</button>}</div>
    {data?.usage.length ? <div className="table-scroll"><table><thead><tr>{isAdmin && <th><input type="checkbox" aria-label="选择本页消费" checked={data.usage.every(row => checkedUsage.includes(row.id))} onChange={e => setCheckedUsage(e.target.checked ? data.usage.map(row => row.id) : [])} /></th>}<th>用户</th><th>任务 ID</th><th>模型</th><th>消费时间</th><th className="right">金额</th>{isAdmin && <th>操作</th>}</tr></thead><tbody>{data.usage.map(row => <tr key={row.id}>{isAdmin && <td><input type="checkbox" aria-label={`选择消费 ${row.id}`} checked={checkedUsage.includes(row.id)} onChange={e => setCheckedUsage(current => e.target.checked ? [...current, row.id] : current.filter(id => id !== row.id))} /></td>}<td>{row.user_name}</td><td className="mono">{row.job_id}</td><td>{row.model}</td><td>{formatDate(row.created_at)}</td><td className="right">{formatMoney(row.amount)}</td>{isAdmin && <td><button className="icon-button danger" title="删除消费记录" onClick={() => remove([], [row.id])}><Trash2 size={16} /></button></td>}</tr>)}</tbody></table></div> : <Empty text="暂无消费记录" />}
    <div className="usage-pagination"><span>第 {page + 1} 页</span><button className="button secondary" disabled={page === 0} onClick={() => setPage(page - 1)}>上一页</button><button className="button secondary" disabled={(page + 1) * limit >= Math.max(data?.ledger_total || 0, data?.usage_total || 0)} onClick={() => setPage(page + 1)}>下一页</button></div>
  </div>
}
