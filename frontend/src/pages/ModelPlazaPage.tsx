import { useEffect, useMemo, useState } from 'react'
import { Search, Store } from 'lucide-react'
import { api, formatMoney } from '../lib/api'
import type { PlazaModel } from '../types'
import { Empty, Notice, PageHeader } from '../components/UI'

export function ModelPlazaPage() {
  const [models, setModels] = useState<PlazaModel[]>([])
  const [search, setSearch] = useState('')
  const [group, setGroup] = useState('')
  const [billing, setBilling] = useState('')
  const [error, setError] = useState('')
  useEffect(() => { api<PlazaModel[]>('/api/public/models').then(setModels).catch(e => setError(e.message)) }, [])
  const groups = useMemo(() => [...new Set(models.map(item => item.group_name))].sort(), [models])
  const visible = models.filter(item => (!search || `${item.name} ${item.group_name}`.toLowerCase().includes(search.trim().toLowerCase())) && (!group || item.group_name === group) && (!billing || item.billing_mode === billing))
  return <div className="page"><PageHeader title="模型广场" subtitle={`${visible.length} 个可用模型`} />
    <div className="catalog-filters"><label className="admin-search"><Search size={16} /><input aria-label="搜索模型" placeholder="搜索模型或分组" value={search} onChange={event => setSearch(event.target.value)} /></label><label>分组<select value={group} onChange={event => setGroup(event.target.value)}><option value="">全部分组</option>{groups.map(name => <option key={name} value={name}>{name}</option>)}</select></label><label>计费方式<select value={billing} onChange={event => setBilling(event.target.value)}><option value="">全部方式</option><option value="fixed">按次</option><option value="anlas">按 Anlas</option></select></label></div>
    {error && <Notice text={error} error />}
    {visible.length ? <div className="catalog-list">{visible.map(item => <article className="catalog-row" key={`${item.group_id}-${item.name}`}><div className="catalog-name"><span className="model-icon"><Store size={17} /></span><strong>{item.name}</strong></div><div className="catalog-group">{item.group_name}<small>{item.is_private ? '专属分组' : '公开分组'}</small></div><div className="catalog-price"><strong>{formatMoney(item.price)}</strong><span> / {item.billing_mode === 'anlas' ? 'Anlas' : '次'}</span>{item.billing_mode === 'anlas' && Number(item.extra_amount) > 0 && <small>另加 {formatMoney(item.extra_amount)} / 次</small>}</div></article>)}</div> : !error && <Empty text="当前筛选下暂无模型" />}
  </div>
}
