import { useEffect, useState, type FormEvent } from 'react'
import { ChevronLeft, ChevronRight, Copy, Plus, Trash2 } from 'lucide-react'
import { api, formatDate, formatMoney, post } from '../lib/api'
import { Empty, Notice } from './UI'

type CodeRow = { id: number; prefix: string; amount: string; created_at: string; redeemed_by: number | null; redeemed_at: string | null }

export function RedemptionManagement() {
  const [rows, setRows] = useState<CodeRow[]>([])
  const [page, setPage] = useState(0)
  const [amount, setAmount] = useState('')
  const [count, setCount] = useState(1)
  const [newCodes, setNewCodes] = useState<string[]>([])
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const load = (currentPage = page) => api<CodeRow[]>(`/api/admin/redemption-codes?offset=${currentPage * 100}&limit=100`).then(setRows).catch(e => setError(e.message))
  useEffect(() => { load(page) }, [page])
  async function create(event: FormEvent) {
    event.preventDefault()
    setBusy(true); setError(''); setMessage('')
    try {
      const result = await post<{ codes: string[] }>('/api/admin/redemption-codes', { amount, count })
      setNewCodes(result.codes); setAmount(''); setCount(1); setPage(0); load(0)
    } catch (e) { setError((e as Error).message) }
    finally { setBusy(false) }
  }
  async function remove(id: number) {
    if (!window.confirm('删除此兑换码？删除后无法使用。')) return
    try { await api(`/api/admin/redemption-codes/${id}`, { method: 'DELETE' }); load() }
    catch (e) { setError((e as Error).message) }
  }
  async function copyCodes() {
    try { await navigator.clipboard.writeText(newCodes.join('\n')); setMessage('兑换码已复制') }
    catch (e) { setError((e as Error).message) }
  }
  return <div>
    {error && <Notice text={error} error />}{message && <Notice text={message} />}
    <form className="inline-form" onSubmit={create}><label>面额 (CNY)<input required type="number" min="0.1001" step="0.0001" value={amount} onChange={e => setAmount(e.target.value)} /></label><label>生成数量<input required type="number" min="1" max="100" value={count} onChange={e => setCount(Number(e.target.value))} /></label><button className="button primary" disabled={busy}><Plus size={16} />生成兑换码</button></form>
    {newCodes.length > 0 && <div className="secret-panel"><span>本次生成的兑换码</span><code className="redemption-codes">{newCodes.join('\n')}</code><button className="icon-button" type="button" title="复制全部兑换码" onClick={copyCodes}><Copy size={17} /></button></div>}
    <div className="section-head"><h2>兑换码列表</h2></div>
    {rows.length ? <div className="table-scroll"><table><thead><tr><th>编号</th><th>兑换码前缀</th><th>面额</th><th>状态</th><th>创建时间</th><th>兑换时间</th><th></th></tr></thead><tbody>{rows.map(row => <tr key={row.id}><td>#{row.id}</td><td className="mono">{row.prefix}...</td><td>{formatMoney(row.amount)}</td><td>{row.redeemed_at ? `已使用 · 用户 #${row.redeemed_by}` : '未使用'}</td><td>{formatDate(row.created_at)}</td><td>{row.redeemed_at ? formatDate(row.redeemed_at) : '-'}</td><td><button className="icon-button danger" title="删除兑换码" onClick={() => remove(row.id)}><Trash2 size={16} /></button></td></tr>)}</tbody></table></div> : <Empty text="暂无兑换码" />}
    <div className="admin-pagination"><span>第 {page + 1} 页</span><button className="icon-button" title="上一页" disabled={page === 0} onClick={() => setPage(page - 1)}><ChevronLeft size={17} /></button><button className="icon-button" title="下一页" disabled={rows.length < 100} onClick={() => setPage(page + 1)}><ChevronRight size={17} /></button></div>
  </div>
}
