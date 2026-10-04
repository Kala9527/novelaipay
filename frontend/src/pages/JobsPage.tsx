import { useEffect, useState } from 'react'
import { RefreshCw, ExternalLink } from 'lucide-react'
import { api, formatDate, formatMoney } from '../lib/api'
import type { Job } from '../types'
import { Empty, Notice, PageHeader, Status } from '../components/UI'

export function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([])
  const [selected, setSelected] = useState<Job | null>(null)
  const [error, setError] = useState('')
  const load = () => api<Job[]>('/api/jobs').then(rows => { setJobs(rows); setSelected(current => rows.find(j => j.id === current?.id) || null) }).catch(e => setError(e.message))
  useEffect(() => { load(); const id = window.setInterval(load, 10000); return () => clearInterval(id) }, [])
  return <div className="page"><PageHeader title="生成任务" subtitle="任务状态每 10 秒更新" action={<button className="button secondary" onClick={load}><RefreshCw size={16} />刷新</button>} />{error && <Notice text={error} error />}{jobs.length ? <div className="table-scroll"><table><thead><tr><th>任务</th><th>模型</th><th>状态</th><th>预留/费用</th><th>提交时间</th></tr></thead><tbody>{jobs.map(job => <tr key={job.id} className="clickable" onClick={() => setSelected(job)}><td className="mono">{job.id.slice(0, 12)}</td><td>{job.model}</td><td><Status value={job.status} /></td><td>{formatMoney(job.amount)}</td><td>{formatDate(job.created_at)}</td></tr>)}</tbody></table></div> : <Empty text="暂无生成任务" />}{selected && <div className="detail-panel"><div className="section-head"><h2>任务详情</h2><button className="icon-button" title="关闭详情" onClick={() => setSelected(null)}>×</button></div><dl className="detail-grid"><dt>任务 ID</dt><dd className="mono">{selected.id}</dd><dt>模型</dt><dd>{selected.model}</dd><dt>尺寸</dt><dd>{selected.size}</dd><dt>状态</dt><dd><Status value={selected.status} /></dd><dt>提示词</dt><dd>{selected.prompt}</dd>{selected.error && <><dt>说明</dt><dd>{selected.error}</dd></>}</dl>{selected.result?.data?.map((image, index) => <a className="result-link" key={index} href={image.url} target="_blank" rel="noreferrer">查看生成图片 <ExternalLink size={15} /></a>)}</div>}</div>
}
