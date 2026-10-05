import { useEffect, useRef, useState, type FormEvent } from 'react'
import { WandSparkles, Plus, Trash2, Download, Image as ImageIcon, Sparkles } from 'lucide-react'
import { api, formatDate, formatMoney } from '../lib/api'
import { recentImages, saveImage, type CachedImage } from '../lib/imageHistory'
import type { Job, Key, Model } from '../types'
import { Notice, Status } from '../components/UI'

type CharacterEntry = { prompt: string; negative_prompt: string; center: number; top: number }

export function JobsPage({ userId }: { userId: number }) {
  const [jobs, setJobs] = useState<Job[]>([])
  const [selected, setSelected] = useState<Job | null>(null)
  const [images, setImages] = useState<(CachedImage & { url: string })[]>([])
  const imageIds = useRef('')
  const [error, setError] = useState('')
  const [models, setModels] = useState<Model[]>([])
  const [keys, setKeys] = useState<Key[]>([])
  const [keyId, setKeyId] = useState('')
  const [busy, setBusy] = useState(false)
  const [pendingReads, setPendingReads] = useState(0)
  const [characters, setCharacters] = useState<CharacterEntry[]>([])
  const [form, setForm] = useState({ key: '', model: '', prompt: '', negative_prompt: '',
    size: '1024x1024', steps: 23, scale: 4, sampler: 'k_euler_ancestral', seed: '',
    smea: false, smea_dyn: false, action: 'generate', image: '', mask: '',
    strength: 0.7, noise: 0, inpaint_img2img_strength: 1,
    reference: '', reference_strength: 0.6,
    reference_info: 1, precise_reference: '', precise_strength: 1,
    precise_fidelity: 1, precise_description: 'character&style',
    noise_schedule: 'karras', cfg_rescale: 0, quality_toggle: false,
    dynamic_thresholding: false, variety_boost: false })
  function updateCharacter(index: number, change: Partial<CharacterEntry>) {
    setCharacters(rows => rows.map((row, current) => current === index ? { ...row, ...change } : row))
  }
  function readImage(file: File | undefined, field: 'image' | 'mask' | 'reference' | 'precise_reference') {
    if (!file) { setForm(current => ({ ...current, [field]: '' })); return }
    const reader = new FileReader()
    setPendingReads(count => count + 1)
    reader.onload = () => setForm(current => ({ ...current, [field]: String(reader.result),
      ...(field === 'reference' ? { precise_reference: '' } : field === 'precise_reference' ? { reference: '' } : {}) }))
    reader.onerror = () => setError('图片读取失败')
    reader.onloadend = () => setPendingReads(count => count - 1)
    reader.readAsDataURL(file)
  }
  async function refreshImages() {
    const cached = await recentImages(userId)
    const ids = cached.map(image => image.id).join(',')
    if (ids === imageIds.current) return
    imageIds.current = ids
    setImages(cached.map(image => ({ ...image, url: URL.createObjectURL(image.blob) })))
  }
  useEffect(() => () => { images.forEach(image => URL.revokeObjectURL(image.url)) }, [images])
  const load = () => api<Job[]>('/api/jobs').then(async rows => {
    setJobs(rows)
    setSelected(current => rows.find(j => j.id === current?.id) || null)
    for (const job of rows.filter(row => row.status === 'succeeded').slice(0, 5)) {
      if (job.result?.data?.length) await saveImage(userId, job)
    }
    await refreshImages()
  }).catch(e => setError(e.message))
  useEffect(() => { load(); const id = window.setInterval(load, 10000); return () => clearInterval(id) }, [userId])
  useEffect(() => { api<Model[]>('/api/models').then(rows => { setModels(rows); if (rows.length) setForm(current => ({ ...current, model: current.model || rows[0].name })) }).catch(e => setError(e.message)) }, [])
  useEffect(() => { api<Key[]>('/api/keys').then(rows => { setKeys(rows); if (rows.length) setKeyId(String(rows[0].id)) }).catch(e => setError(e.message)) }, [])
  const availableModels = models.filter(row => !keyId || row.group_id === keys.find(key => key.id === Number(keyId))?.group_id)
  useEffect(() => { if (availableModels.length && !availableModels.some(row => row.name === form.model)) setForm(current => ({ ...current, model: availableModels[0].name })) }, [keyId, models, keys])
  async function generate(event: FormEvent) {
    event.preventDefault(); setError(''); setBusy(true)
    try {
      const key = keyId ? (await api<{ key: string }>(`/api/keys/${keyId}/secret`)).key : form.key
      const response = await fetch('/v1/images/generations', {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${key}`,
          'Idempotency-Key': crypto.randomUUID() },
        body: JSON.stringify({ model: form.model, prompt: form.prompt, size: form.size,
          parameters: { steps: Number(form.steps), scale: Number(form.scale), sampler: form.sampler,
            negative_prompt: form.negative_prompt, seed: form.seed ? Number(form.seed) : null,
            smea: form.smea, smea_dyn: form.smea_dyn, action: form.action,
            image: form.action === 'generate' ? null : form.image,
            mask: form.action === 'infill' ? form.mask : null,
            strength: Number(form.strength), noise: Number(form.noise),
            inpaint_img2img_strength: form.action === 'infill' ? Number(form.inpaint_img2img_strength) : null,
            references: form.reference ? [{ image: form.reference, strength: Number(form.reference_strength), information_extracted: Number(form.reference_info) }] : [],
            precise_reference: form.precise_reference ? { image: form.precise_reference, strength: Number(form.precise_strength),
              fidelity: Number(form.precise_fidelity), description: form.precise_description, information_extracted: 1 } : null,
            character_prompts: characters,
            noise_schedule: form.noise_schedule, cfg_rescale: Number(form.cfg_rescale),
            quality_toggle: form.quality_toggle, dynamic_thresholding: form.dynamic_thresholding,
            variety_boost: form.variety_boost } }),
      })
      const result = await response.json()
      if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : '提交失败')
      setForm(current => ({ ...current, key: '' }))
      await load()
      setSelected(result as Job)
    } catch (e) { setError((e as Error).message) }
    finally { setBusy(false) }
  }
  const model = availableModels.find(row => row.name === form.model)
  return <div className="studio-page">
    <header className="studio-header"><div><span className="studio-eyebrow"><Sparkles size={13} /> IMAGE STUDIO</span><h1>生图工作台</h1></div><div className="studio-header-meta">{model && <span>{model.name}</span>}<span>{model ? `${formatMoney(model.price)} / ${model.billing_mode === 'anlas' ? 'Anlas' : '次'}${Number(model.extra_amount) ? ` + ${formatMoney(model.extra_amount)} / 次` : ''}` : '选择模型'}</span></div></header>
    {error && <Notice text={error} error />}
    <div className="studio-grid">
    {models.length > 0 && <form className="form-grid studio-controls" onSubmit={generate}>
      <label>模型<select required value={form.model} onChange={e => setForm(current => ({ ...current, model: e.target.value, smea: false, smea_dyn: false }))}>{availableModels.map(model => <option key={`${model.group_id}-${model.name}`} value={model.name}>{model.name}</option>)}</select></label>
      <label>API 密钥{keys.length ? <select required value={keyId} onChange={e => setKeyId(e.target.value)}>{keys.map(key => <option key={key.id} value={key.id}>{key.name} · {key.prefix}</option>)}</select> : <input type="password" required autoComplete="off" value={form.key} onChange={e => setForm({ ...form, key: e.target.value })} placeholder="先在 API 密钥页面创建密钥" />}</label>
      <label className="wide">提示词<textarea required value={form.prompt} onChange={e => setForm({ ...form, prompt: e.target.value })} /></label>
      <label className="wide">排除内容<textarea value={form.negative_prompt} onChange={e => setForm({ ...form, negative_prompt: e.target.value })} /></label>
      <div className="wide studio-mode"><span>生成模式</span><div className="studio-segments">{[['generate', '文生图'], ['img2img', '图生图'], ['infill', '局部重绘']].map(([value, label]) => <button key={value} type="button" className={form.action === value ? 'active' : ''} onClick={() => setForm(current => ({ ...current, action: value, image: '', mask: '' }))}>{label}</button>)}</div></div>
      {form.action !== 'generate' && <><label>原图<input type="file" accept="image/png,image/jpeg" required onChange={e => readImage(e.target.files?.[0], 'image')} /></label>
        {form.action === 'infill' && <label>遮罩 PNG<input type="file" accept="image/png" required onChange={e => readImage(e.target.files?.[0], 'mask')} /></label>}
        <label>重绘强度<input type="number" min="0" max="1" step="0.01" value={form.strength} onChange={e => setForm({ ...form, strength: Number(e.target.value) })} /></label>
        <label>噪声<input type="number" min="0" max="1" step="0.01" value={form.noise} onChange={e => setForm({ ...form, noise: Number(e.target.value) })} /></label></>}
      {form.action === 'infill' && <label>局部重绘保留强度<input type="number" min="0" max="1" step="0.01" value={form.inpaint_img2img_strength} onChange={e => setForm({ ...form, inpaint_img2img_strength: Number(e.target.value) })} /></label>}
      <label>尺寸<select value={form.size} onChange={e => setForm({ ...form, size: e.target.value })}><option>1024x1024</option><option>832x1216</option><option>1216x832</option><option>768x1152</option><option>1152x768</option><option>512x512</option></select></label>
      <label>步数<input type="number" min="1" max="50" value={form.steps} onChange={e => setForm({ ...form, steps: Number(e.target.value) })} /></label>
      <label>提示词引导<input type="number" min="0" max="30" step="0.1" value={form.scale} onChange={e => setForm({ ...form, scale: Number(e.target.value) })} /></label>
      <label>采样器<select value={form.sampler} onChange={e => setForm({ ...form, sampler: e.target.value })}><option value="k_euler_ancestral">Euler Ancestral</option><option value="k_euler">Euler</option><option value="k_dpmpp_2m">DPM++ 2M</option><option value="k_dpmpp_sde">DPM++ SDE</option><option value="ddim">DDIM</option></select></label>
      <label>种子<input type="number" min="0" max="4294967295" placeholder="随机" value={form.seed} onChange={e => setForm({ ...form, seed: e.target.value })} /></label>
      <label>噪声调度<select value={form.noise_schedule} onChange={e => setForm({ ...form, noise_schedule: e.target.value })}><option value="karras">Karras</option><option value="native">Native</option><option value="exponential">Exponential</option><option value="polyexponential">Polyexponential</option></select></label>
      <label>CFG 重调<input type="number" min="0" max="1" step="0.01" value={form.cfg_rescale} onChange={e => setForm({ ...form, cfg_rescale: Number(e.target.value) })} /></label>
      <label>Vibe 参考图<input type="file" accept="image/png,image/jpeg" onChange={e => readImage(e.target.files?.[0], 'reference')} /></label>
      {form.reference && <><label>Vibe 强度<input type="number" min="0" max="1" step="0.01" value={form.reference_strength} onChange={e => setForm({ ...form, reference_strength: Number(e.target.value) })} /></label>
      <label>提取信息<input type="number" min="0" max="1" step="0.01" value={form.reference_info} onChange={e => setForm({ ...form, reference_info: Number(e.target.value) })} /></label></>}
      <label>精准参考图<input type="file" accept="image/png,image/jpeg" onChange={e => readImage(e.target.files?.[0], 'precise_reference')} /></label>
      {form.precise_reference && <><label>精准参考强度<input type="number" min="0" max="1" step="0.01" value={form.precise_strength} onChange={e => setForm({ ...form, precise_strength: Number(e.target.value) })} /></label>
        <label>保真度<input type="number" min="0" max="1" step="0.01" value={form.precise_fidelity} onChange={e => setForm({ ...form, precise_fidelity: Number(e.target.value) })} /></label>
        <label>参考内容<select value={form.precise_description} onChange={e => setForm({ ...form, precise_description: e.target.value })}><option value="character&style">角色和画风</option><option value="character">仅角色</option><option value="style">仅画风</option></select></label></>}
      {characters.map((character, index) => <div className="wide" key={index}><div className="section-head"><h3>角色 {index + 1}</h3><button type="button" className="icon-button" title="移除角色" onClick={() => setCharacters(rows => rows.filter((_, current) => current !== index))}><Trash2 size={16} /></button></div>
        <div className="form-grid"><label className="wide">角色提示词<input required value={character.prompt} onChange={e => updateCharacter(index, { prompt: e.target.value })} /></label>
          <label>角色排除词<input value={character.negative_prompt} onChange={e => updateCharacter(index, { negative_prompt: e.target.value })} /></label>
          <label>水平位置<input type="number" min="0" max="1" step="0.01" value={character.center} onChange={e => updateCharacter(index, { center: Number(e.target.value) })} /></label>
          <label>垂直位置<input type="number" min="0" max="1" step="0.01" value={character.top} onChange={e => updateCharacter(index, { top: Number(e.target.value) })} /></label></div></div>)}
      <button type="button" className="button secondary" disabled={characters.length >= 6} onClick={() => setCharacters(rows => [...rows, { prompt: '', negative_prompt: '', center: 0.5, top: 0.5 }])}><Plus size={16} />添加角色</button>
      <label className="check-label"><input type="checkbox" checked={form.quality_toggle} onChange={e => setForm({ ...form, quality_toggle: e.target.checked })} />质量标签</label>
      <label className="check-label"><input type="checkbox" checked={form.dynamic_thresholding} onChange={e => setForm({ ...form, dynamic_thresholding: e.target.checked })} />动态阈值</label>
      <label className="check-label"><input type="checkbox" checked={form.variety_boost} onChange={e => setForm({ ...form, variety_boost: e.target.checked })} />Variety+</label>
      <label className="check-label" title={model?.supports_smea ? '' : '当前模型不支持 SMEA'}><input type="checkbox" disabled={!model?.supports_smea} checked={form.smea && !!model?.supports_smea} onChange={e => setForm({ ...form, smea: e.target.checked, smea_dyn: e.target.checked ? form.smea_dyn : false })} />SMEA</label>
      <label className="check-label" title={model?.supports_smea ? '' : '当前模型不支持 SMEA DYN'}><input type="checkbox" disabled={!model?.supports_smea || !form.smea} checked={form.smea_dyn && !!model?.supports_smea} onChange={e => setForm({ ...form, smea_dyn: e.target.checked })} />SMEA DYN</label>
      <button className="button primary studio-generate" disabled={busy || pendingReads > 0 || !model}><WandSparkles size={16} />{busy ? '提交中' : pendingReads > 0 ? '读取图片中' : '生成图片'}</button>
    </form>}
    <section className="studio-canvas"><div className="studio-pane-title"><span>预览</span>{selected && <Status value={selected.status} />}</div>{selected?.result?.data?.[0]?.url ? <div className="studio-result"><img src={selected.result.data[0].url} alt={selected.prompt} /><a className="button secondary" href={selected.result.data[0].url} download={`${selected.id}.png`}><Download size={16} />下载图片</a></div> : <div className="studio-empty"><ImageIcon size={48} strokeWidth={1.3} /><strong>{selected?.status === 'running' || selected?.status === 'queued' ? '正在生成图片' : '暂无生成结果'}</strong>{selected?.error && <span>{selected.error}</span>}</div>}{selected && <div className="studio-result-meta"><span>{selected.model}</span><span>{selected.size}</span><span>{formatMoney(selected.amount)}</span></div>}</section>
    <aside className="studio-history"><div className="studio-pane-title"><span>最近生成</span><small>{images.length} / 5</small></div>{images.length ? <div className="studio-history-list">{images.map(image => <button type="button" className="studio-history-item" key={image.id} onClick={() => setSelected(jobs.find(job => job.id === image.id) || null)}><img src={image.url} alt="" /><span><strong>{image.model}</strong><small>{formatDate(image.createdAt)}</small></span></button>)}</div> : <div className="studio-history-empty"><ImageIcon size={26} /><span>{jobs.some(job => ['queued', 'running'].includes(job.status)) ? '图片生成中' : '暂无本地图片'}</span></div>}</aside>
    </div>
  </div>
}
