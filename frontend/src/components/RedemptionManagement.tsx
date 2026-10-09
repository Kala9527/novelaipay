import { useEffect, useState, type FormEvent } from 'react'
import { ChevronLeft, ChevronRight, Copy, Download, Plus, Trash2 } from 'lucide-react'
import { api, downloadCsv, formatDate, formatMoney, post } from '../lib/api'
import { copyText } from '../lib/clipboard'
import { Empty, Notice } from './UI'

type CodeRow = { id: number; prefix: string; can_copy: boolean; amount: string; created_at: string; redeemed_by: number | null; redeemed_at: string | null }

export function RedemptionManagement() {
  const [rows, setRows] = useState<CodeRow[]>([])
  const [page, setPage] = useState(0)
  const [amount, setAmount] = useState('')
  const [count, setCount] = useState(1)
  const [newCodes, setNewCodes] = useState<string[]>([])
  const [checked, setChecked] = useState<number[]>([])
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const load = (currentPage = page) => api<CodeRow[]>(`/api/admin/redemption-codes?offset=${currentPage * 100}&limit=100`).then(result => {
    setRows(result)
    setChecked(current => current.filter(id => result.some(row => row.id === id)))
  }).catch(e => setError(e.message))
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
    try { await copyText(newCodes.join('\n')); setMessage('兑换码已复制') }
    catch (e) { setError((e as Error).message) }
  }
  async function copyCode(id: number) {
    try {
      const result = await api<{ code: string }>(`/api/admin/redemption-codes/${id}/secret`)
      await copyText(result.code)
      setMessage('兑换码已复制')
    } catch (e) { setError((e as Error).message) }
  }
  async function exportCodes(ids?: number[]) {
    const query = new URLSearchParams()
    ids?.forEach(id => query.append('ids', String(id)))
    try { await downloadCsv(`/api/admin/redemption-codes/export${query.size ? `?${query}` : ''}`, 'redemption-codes.csv') }
    catch (e) { setError((e as Error).message) }
  }
  const allChecked = rows.length > 0 && rows.every(row => checked.includes(row.id))
  return <div>
    {error && <Notice text={error} error />}{message && <Notice text={message} />}
    <form className="inline-form" onSubmit={create}><label>面额 (CNY)<input required type="number" min="0.1001" step="0.0001" value={amount} onChange={e => setAmount(e.target.value)} /></label><label>生成数量<input required type="number" min="1" max="100" value={count} onChange={e => setCount(Number(e.target.value))} /></label><button className="button primary" disabled={busy}><Plus size={16} />生成兑换码</button></form>
    {newCodes.length > 0 && <div className="secret-panel"><span>本次生成的兑换码</span><code className="redemption-codes">{newCodes.join('\n')}</code><button className="icon-button" type="button" title="复制全部兑换码" onClick={copyCodes}><Copy size={17} /></button></div>}
    <div className="section-head export-section-head"><h2>兑换码列表</h2><div className="button-group">{checked.length > 0 && <button className="button secondary" onClick={() => exportCodes(checked)}><Download size={15} />导出选中 ({checked.length})</button>}<button className="button secondary" onClick={() => exportCodes()}><Download size={15} />导出全部</button></div></div>
    {rows.length ? <div className="table-scroll"><table><thead><tr><th><input type="checkbox" aria-label="选择本页兑换码" checked={allChecked} onChange={e => setChecked(e.target.checked ? rows.map(row => row.id) : [])} /></th><th>编号</th><th>兑换码前缀</th><th>面额</th><th>状态</th><th>创建时间</th><th>兑换时间</th><th>操作</th></tr></thead><tbody>{rows.map(row => <tr key={row.id}><td><input type="checkbox" aria-label={`选择兑换码 ${row.id}`} checked={checked.includes(row.id)} onChange={e => setChecked(current => e.target.checked ? [...current, row.id] : current.filter(id => id !== row.id))} /></td><td>#{row.id}</td><td className="mono">{row.prefix}...{!row.can_copy && <div className="muted">旧码无法恢复</div>}</td><td>{formatMoney(row.amount)}</td><td>{row.redeemed_at ? `已使用 · 用户 #${row.redeemed_by}` : '未使用'}</td><td>{formatDate(row.created_at)}</td><td>{row.redeemed_at ? formatDate(row.redeemed_at) : '-'}</td><td><div className="row-actions"><button className="icon-button" title={row.can_copy ? '复制兑换码' : '旧兑换码无法恢复，请重新生成'} disabled={!row.can_copy} onClick={() => copyCode(row.id)}><Copy size={16} /></button><button className="icon-button danger" title="删除兑换码" onClick={() => remove(row.id)}><Trash2 size={16} /></button></div></td></tr>)}</tbody></table></div> : <Empty text="暂无兑换码" />}
    <div className="admin-pagination"><span>第 {page + 1} 页</span><button className="icon-button" title="上一页" disabled={page === 0} onClick={() => setPage(page - 1)}><ChevronLeft size={17} /></button><button className="icon-button" title="下一页" disabled={rows.length < 100} onClick={() => setPage(page + 1)}><ChevronRight size={17} /></button></div>
  </div>
}
