import { useEffect, useState } from 'react'
import { api, formatDate, formatMoney } from '../lib/api'
import type { Billing } from '../types'
import { Empty, PageHeader } from '../components/UI'

export function BillingPage() {
  const [data, setData] = useState<Billing | null>(null)
  useEffect(() => { api<Billing>('/api/billing').then(setData) }, [])
  return <div className="page"><PageHeader title="账单流水" subtitle="按账户查看充值和逐次消费" /><div className="balance-band"><div><span>账户余额</span><strong>{formatMoney(data?.balance || '0')}</strong></div><div><span>任务预留</span><strong>{formatMoney(data?.reserved || '0')}</strong></div><div><span>可用余额</span><strong>{formatMoney(Number(data?.balance || 0) - Number(data?.reserved || 0))}</strong></div></div><div className="section-head"><h2>资金流水</h2></div>{data?.ledger.length ? <div className="table-scroll"><table><thead><tr><th>类型</th><th>关联记录</th><th>时间</th><th className="right">金额</th></tr></thead><tbody>{data.ledger.map(row => <tr key={row.id}><td>{row.kind === 'usage' ? '生图消费' : row.kind === 'payment' ? '支付充值' : '管理员入账'}</td><td className="mono">{row.reference}</td><td>{formatDate(row.created_at)}</td><td className={`right money ${Number(row.amount) > 0 ? 'positive' : ''}`}>{Number(row.amount) > 0 ? '+' : ''}{formatMoney(row.amount)}</td></tr>)}</tbody></table></div> : <Empty text="暂无资金流水" />}<div className="section-head"><h2>消费记录</h2></div>{data?.usage.length ? <div className="table-scroll"><table><thead><tr><th>任务 ID</th><th>价格版本</th><th>消费时间</th><th className="right">金额</th></tr></thead><tbody>{data.usage.map(row => <tr key={row.job_id}><td className="mono">{row.job_id}</td><td>#{row.price_version_id}</td><td>{formatDate(row.created_at)}</td><td className="right">{formatMoney(row.amount)}</td></tr>)}</tbody></table></div> : <Empty text="暂无消费记录" />}</div>
}
