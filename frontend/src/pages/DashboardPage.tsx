import { useEffect, useState } from 'react'
import { ArrowUpRight, Clock3, Coins, Images, KeyRound } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api, formatDate, formatMoney } from '../lib/api'
import type { Job, Model, User } from '../types'
import { Empty, PageHeader, Status } from '../components/UI'

export function DashboardPage({ user }: { user: User }) {
  const [models, setModels] = useState<Model[]>([])
  const [jobs, setJobs] = useState<Job[]>([])
  useEffect(() => {
    api<Model[]>('/api/models').then(setModels)
    api<Job[]>('/api/jobs').then(setJobs)
  }, [])

  const active = jobs.filter(job => ['queued', 'running', 'uncertain'].includes(job.status)).length

  return <div className="page">
    <PageHeader title="概览" subtitle={`欢迎回来，${user.name || user.email}`} />
    <div className="metric-grid">
      <div className="metric"><span><Coins size={18} />可用余额</span><strong>{formatMoney(Number(user.balance) - Number(user.reserved))}</strong><small>已预留 {formatMoney(user.reserved)}</small></div>
      <div className="metric"><span><Images size={18} />生成任务</span><strong>{jobs.length}</strong><small>最近 100 条任务</small></div>
      <div className="metric"><span><Clock3 size={18} />进行中</span><strong>{active}</strong><small>按分组和上游容量排队</small></div>
    </div>
    <div className="section-head"><h2>可用模型</h2><Link to="/keys" className="text-link">管理密钥 <ArrowUpRight size={15} /></Link></div>
    {models.length ? <div className="model-list">{models.map(model => <div className="model-row" key={`${model.group_id}-${model.name}`}><div className="model-icon"><Images size={18} /></div><div><strong>{model.name}</strong><span>分组 #{model.group_id}</span></div><b>{formatMoney(model.price)} <small>/ {model.billing_mode === 'anlas' ? 'Anlas' : '次'}{Number(model.extra_amount) > 0 && ` + ${formatMoney(model.extra_amount)} / 次`}</small></b></div>)}</div> : <Empty text="管理员尚未发布模型" />}
    <div className="section-head"><h2>最近任务</h2><Link to="/jobs" className="text-link">查看全部 <ArrowUpRight size={15} /></Link></div>
    {jobs.length ? <div className="table-scroll"><table><thead><tr><th>任务 ID</th><th>模型</th><th>状态</th><th>时间</th><th>费用</th></tr></thead><tbody>{jobs.slice(0, 5).map(job => <tr key={job.id}><td className="mono">{job.id.slice(0, 8)}</td><td>{job.model}</td><td><Status value={job.status} /></td><td>{formatDate(job.created_at)}</td><td>{formatMoney(job.amount)}</td></tr>)}</tbody></table></div> : <div className="empty-state"><KeyRound size={20} /> 创建 API 密钥后即可提交任务</div>}
  </div>
}
