import { useEffect, useState } from 'react'
import { ArrowRight, ArrowUpRight, Clock3, Coins, Images, KeyRound, WandSparkles } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api, formatDate, formatMoney } from '../lib/api'
import type { Job, Model, User } from '../types'
import { Empty, PageHeader, Status } from '../components/UI'
import { usePreferences } from '../lib/preferences'

export function DashboardPage({ user }: { user: User }) {
  const { t } = usePreferences()
  const [models, setModels] = useState<Model[]>([])
  const [jobs, setJobs] = useState<Job[]>([])
  useEffect(() => {
    api<Model[]>('/api/models').then(setModels)
    api<Job[]>('/api/jobs').then(setJobs)
  }, [])

  const active = jobs.filter(job => ['queued', 'running', 'uncertain'].includes(job.status)).length

  return <div className="page">
    <PageHeader title={t('overview')} subtitle={t('dashboardSubtitle', { name: user.name || user.email })} action={<Link to="/workshop" className="button primary"><WandSparkles size={16} />{t('getStarted')}</Link>} />
    <div className="dashboard-shortcuts"><Link to="/quickstart"><span>01</span>{t('quickstart')}<ArrowRight size={15} /></Link><Link to="/models"><span>02</span>{t('models')}<ArrowRight size={15} /></Link><Link to="/api-guide"><span>03</span>{t('guide')}<ArrowRight size={15} /></Link></div>
    <div className="metric-grid">
      <div className="metric"><span><Coins size={18} />{t('availableBalance')}</span><strong>{formatMoney(Number(user.balance) - Number(user.reserved))}</strong><small>{t('reserved', { value: formatMoney(user.reserved) })}</small></div>
      <div className="metric"><span><Images size={18} />{t('generatedJobs')}</span><strong>{jobs.length}</strong><small>{t('recentJobs')}</small></div>
      <div className="metric"><span><Clock3 size={18} />{t('inProgress')}</span><strong>{active}</strong><small>{t('queueHint')}</small></div>
    </div>
    <div className="section-head"><h2>{t('availableModels')}</h2><Link to="/keys" className="text-link">{t('manageKeys')} <ArrowUpRight size={15} /></Link></div>
    {models.length ? <div className="model-list">{models.map(model => <div className="model-row" key={`${model.group_id}-${model.name}`}><div className="model-icon"><Images size={18} /></div><div><strong>{model.name}</strong><span>{t('group')} #{model.group_id}</span></div><b>{formatMoney(model.price)} <small>/ {model.billing_mode === 'anlas' ? 'Anlas' : t('perRun')}{Number(model.extra_amount) > 0 && ` + ${formatMoney(model.extra_amount)} / ${t('perRun')}`}</small></b></div>)}</div> : <Empty text={t('noModels')} />}
    <div className="section-head"><h2>{t('recentTasks')}</h2><Link to="/jobs" className="text-link">{t('viewAll')} <ArrowUpRight size={15} /></Link></div>
    {jobs.length ? <div className="table-scroll"><table><thead><tr><th>{t('taskId')}</th><th>{t('model')}</th><th>{t('status')}</th><th>{t('time')}</th><th>{t('cost')}</th></tr></thead><tbody>{jobs.slice(0, 5).map(job => <tr key={job.id}><td className="mono">{job.id.slice(0, 8)}</td><td>{job.model}</td><td><Status value={job.status} /></td><td>{formatDate(job.created_at)}</td><td>{formatMoney(job.amount)}</td></tr>)}</tbody></table></div> : <div className="empty-state"><KeyRound size={20} /> {t('createKeyHint')}</div>}
  </div>
}
