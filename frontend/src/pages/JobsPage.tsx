import { useEffect, useState, type FormEvent } from 'react'
import { RefreshCw, ExternalLink, WandSparkles } from 'lucide-react'
import { api, formatDate, formatMoney } from '../lib/api'
import type { Job, Model } from '../types'
import { Empty, Notice, PageHeader, Status } from '../components/UI'

export function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([])
  const [selected, setSelected] = useState<Job | null>(null)
  const [error, setError] = useState('')
  const [models, setModels] = useState<Model[]>([])
  const [busy, setBusy] = useState(false)
  const [form, setForm] = useState({ key: '', model: '', prompt: '', negative_prompt: '',
    size: '1024x1024', steps: 23, scale: 4, sampler: 'k_euler_ancestral', seed: '',
    smea: false, smea_dyn: false })
  const load = () => api<Job[]>('/api/jobs').then(rows => { setJobs(rows); setSelected(current => rows.find(j => j.id === current?.id) || null) }).catch(e => setError(e.message))
  useEffect(() => { load(); const id = window.setInterval(load, 10000); return () => clearInterval(id) }, [])
  useEffect(() => { api<Model[]>('/api/models').then(rows => { setModels(rows); if (rows.length) setForm(current => ({ ...current, model: current.model || rows[0].name })) }).catch(e => setError(e.message)) }, [])
  async function generate(event: FormEvent) {
    event.preventDefault(); setError(''); setBusy(true)
    try {
      const response = await fetch('/v1/images/generations', {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${form.key}`,
          'Idempotency-Key': crypto.randomUUID() },
        body: JSON.stringify({ model: form.model, prompt: form.prompt, size: form.size,
          parameters: { steps: Number(form.steps), scale: Number(form.scale), sampler: form.sampler,
            negative_prompt: form.negative_prompt, seed: form.seed ? Number(form.seed) : null,
            smea: form.smea, smea_dyn: form.smea_dyn } }),
      })
      const result = await response.json()
      if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : '提交失败')
      setForm(current => ({ ...current, key: '' }))
      await load()
      setSelected(result as Job)
    } catch (e) { setError((e as Error).message) }
    finally { setBusy(false) }
  }
  return <div className="page"><PageHeader title="生成任务" subtitle="任务状态每 10 秒更新" action={<button className="button secondary" onClick={load}><RefreshCw size={16} />刷新</button>} />
    {models.length > 0 && <><div className="section-head"><h2>创建图片</h2></div><form className="form-grid" onSubmit={generate}>
      <label>模型<select required value={form.model} onChange={e => setForm({ ...form, model: e.target.value })}>{models.map(model => <option key={model.name} value={model.name}>{model.name}</option>)}</select></label>
      <label>API 密钥<input type="password" required autoComplete="off" value={form.key} onChange={e => setForm({ ...form, key: e.target.value })} /></label>
      <label className="wide">提示词<textarea required value={form.prompt} onChange={e => setForm({ ...form, prompt: e.target.value })} /></label>
      <label className="wide">排除内容<textarea value={form.negative_prompt} onChange={e => setForm({ ...form, negative_prompt: e.target.value })} /></label>
      <label>尺寸<select value={form.size} onChange={e => setForm({ ...form, size: e.target.value })}><option>1024x1024</option><option>832x1216</option><option>1216x832</option><option>768x1152</option><option>1152x768</option><option>512x512</option></select></label>
      <label>步数<input type="number" min="1" max="50" value={form.steps} onChange={e => setForm({ ...form, steps: Number(e.target.value) })} /></label>
      <label>提示词引导<input type="number" min="0" max="30" step="0.1" value={form.scale} onChange={e => setForm({ ...form, scale: Number(e.target.value) })} /></label>
      <label>采样器<select value={form.sampler} onChange={e => setForm({ ...form, sampler: e.target.value })}><option value="k_euler_ancestral">Euler Ancestral</option><option value="k_euler">Euler</option><option value="k_dpmpp_2m">DPM++ 2M</option><option value="k_dpmpp_sde">DPM++ SDE</option><option value="ddim">DDIM</option></select></label>
      <label>种子<input type="number" min="0" max="4294967295" placeholder="随机" value={form.seed} onChange={e => setForm({ ...form, seed: e.target.value })} /></label>
      <label className="check-label"><input type="checkbox" checked={form.smea} onChange={e => setForm({ ...form, smea: e.target.checked, smea_dyn: e.target.checked ? form.smea_dyn : false })} />SMEA</label>
      <label className="check-label"><input type="checkbox" disabled={!form.smea} checked={form.smea_dyn} onChange={e => setForm({ ...form, smea_dyn: e.target.checked })} />SMEA DYN</label>
      <button className="button primary" disabled={busy}><WandSparkles size={16} />{busy ? '提交中' : '生成图片'}</button>
    </form></>}
    {error && <Notice text={error} error />}{jobs.length ? <div className="table-scroll"><table><thead><tr><th>任务</th><th>模型</th><th>状态</th><th>预留/费用</th><th>提交时间</th></tr></thead><tbody>{jobs.map(job => <tr key={job.id} className="clickable" onClick={() => setSelected(job)}><td className="mono">{job.id.slice(0, 12)}</td><td>{job.model}</td><td><Status value={job.status} /></td><td>{formatMoney(job.amount)}</td><td>{formatDate(job.created_at)}</td></tr>)}</tbody></table></div> : <Empty text="暂无生成任务" />}{selected && <div className="detail-panel"><div className="section-head"><h2>任务详情</h2><button className="icon-button" title="关闭详情" onClick={() => setSelected(null)}>×</button></div><dl className="detail-grid"><dt>任务 ID</dt><dd className="mono">{selected.id}</dd><dt>模型</dt><dd>{selected.model}</dd><dt>尺寸</dt><dd>{selected.size}</dd><dt>状态</dt><dd><Status value={selected.status} /></dd><dt>Anlas</dt><dd>{selected.anlas_cost ?? '-'}</dd><dt>提示词</dt><dd>{selected.prompt}</dd>{selected.error && <><dt>说明</dt><dd>{selected.error}</dd></>}</dl>{selected.result?.data?.map((image, index) => <a className="result-link" key={index} href={image.url} target="_blank" rel="noreferrer">查看生成图片 <ExternalLink size={15} /></a>)}</div>}</div>
}
