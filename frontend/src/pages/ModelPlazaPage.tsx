import { useEffect, useMemo, useState } from 'react'
import { Check, ChevronDown, ChevronRight, Copy, Grid2X2, List, RotateCcw, Search, Store, X } from 'lucide-react'
import { api, formatMoney } from '../lib/api'
import type { PlazaModel } from '../types'
import { Empty, Notice } from '../components/UI'

type BillingFilter = '' | 'fixed' | 'anlas'
type ScopeFilter = '' | 'public' | 'private'
type SortBy = 'name' | 'price'

function priceLabel(item: PlazaModel) {
  return item.billing_mode === 'anlas' ? `${formatMoney(item.price)} / Anlas` : `${formatMoney(item.price)} / 次`
}

export function ModelPlazaPage() {
  const [models, setModels] = useState<PlazaModel[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [group, setGroup] = useState('')
  const [billing, setBilling] = useState<BillingFilter>('')
  const [scope, setScope] = useState<ScopeFilter>('')
  const [sortBy, setSortBy] = useState<SortBy>('name')
  const [ascending, setAscending] = useState(true)
  const [view, setView] = useState<'grid' | 'list'>('grid')
  const [expanded, setExpanded] = useState({ group: true, billing: true, scope: true })
  const [selected, setSelected] = useState<PlazaModel | null>(null)
  const [copiedName, setCopiedName] = useState<string | null>(null)
  const [error, setError] = useState('')

  useEffect(() => { api<PlazaModel[]>('/api/public/models').then(setModels).catch(e => setError(e.message)).finally(() => setLoading(false)) }, [])
  useEffect(() => {
    if (!selected) return
    const close = (event: KeyboardEvent) => { if (event.key === 'Escape') setSelected(null) }
    window.addEventListener('keydown', close)
    return () => window.removeEventListener('keydown', close)
  }, [selected])

  const groups = useMemo(() => [...new Set(models.map(item => item.group_name))].sort((a, b) => a.localeCompare(b)), [models])
  const searchedModels = useMemo(() => models.filter(item => item.name.toLowerCase().includes(search.trim().toLowerCase())), [models, search])
  const groupModels = useMemo(() => searchedModels.filter(item => !group || item.group_name === group), [searchedModels, group])
  const billedModels = useMemo(() => groupModels.filter(item => !billing || item.billing_mode === billing), [groupModels, billing])
  const visible = useMemo(() => billedModels.filter(item =>
    (!scope || (scope === 'private' ? item.is_private : !item.is_private))
  ).sort((a, b) => {
    const result = sortBy === 'price' ? Number(a.price) - Number(b.price) : a.name.localeCompare(b.name)
    return ascending ? result : -result
  }), [billedModels, scope, sortBy, ascending])

  const count = (items: PlazaModel[], predicate: (item: PlazaModel) => boolean) => items.filter(predicate).length
  function reset() { setSearch(''); setGroup(''); setBilling(''); setScope('') }
  function changeSort(value: SortBy) { if (sortBy === value) setAscending(current => !current); else { setSortBy(value); setAscending(true) } }
  function toggleSection(key: keyof typeof expanded) { setExpanded(current => ({ ...current, [key]: !current[key] })) }
  async function copyName(name: string) {
    try {
      await navigator.clipboard.writeText(name)
      setCopiedName(name)
      window.setTimeout(() => setCopiedName(current => current === name ? null : current), 1800)
    } catch { setCopiedName(null) }
  }

  return <div className="catalog-page">
    <div className="catalog-page-header"><h1>模型广场</h1><p>浏览可用模型与分组定价</p></div>
    <aside className="catalog-sidebar" aria-label="模型筛选">
      <div className="catalog-filter-heading"><div><strong>筛选</strong><p>按分组、计费和权限筛选模型</p></div><button className="catalog-reset" type="button" onClick={reset}><RotateCcw size={14} />重置</button></div>
      <section className="catalog-filter-section"><h2><button type="button" aria-expanded={expanded.group} onClick={() => toggleSection('group')}>分组 <ChevronDown size={15} /></button></h2>{expanded.group && <div className="catalog-filter-options">
        <button type="button" className={!group ? 'selected' : ''} onClick={() => setGroup('')}>所有分组 <span>{searchedModels.length}</span></button>
        {groups.map(name => <button type="button" key={name} className={group === name ? 'selected' : ''} onClick={() => setGroup(name)}>{name} <span>{count(searchedModels, item => item.group_name === name)}</span></button>)}
      </div>}</section>
      <section className="catalog-filter-section"><h2><button type="button" aria-expanded={expanded.billing} onClick={() => toggleSection('billing')}>计费类型 <ChevronDown size={15} /></button></h2>{expanded.billing && <div className="catalog-filter-options">
        <button type="button" className={!billing ? 'selected' : ''} onClick={() => setBilling('')}>所有类型 <span>{groupModels.length}</span></button>
        <button type="button" className={billing === 'fixed' ? 'selected' : ''} onClick={() => setBilling('fixed')}>按次计费 <span>{count(groupModels, item => item.billing_mode === 'fixed')}</span></button>
        <button type="button" className={billing === 'anlas' ? 'selected' : ''} onClick={() => setBilling('anlas')}>按 Anlas <span>{count(groupModels, item => item.billing_mode === 'anlas')}</span></button>
      </div>}</section>
      <section className="catalog-filter-section"><h2><button type="button" aria-expanded={expanded.scope} onClick={() => toggleSection('scope')}>可见范围 <ChevronDown size={15} /></button></h2>{expanded.scope && <div className="catalog-filter-options">
        <button type="button" className={!scope ? 'selected' : ''} onClick={() => setScope('')}>全部 <span>{billedModels.length}</span></button>
        <button type="button" className={scope === 'public' ? 'selected' : ''} onClick={() => setScope('public')}>公开分组 <span>{count(billedModels, item => !item.is_private)}</span></button>
        {models.some(item => item.is_private) && <button type="button" className={scope === 'private' ? 'selected' : ''} onClick={() => setScope('private')}>专属分组 <span>{count(billedModels, item => item.is_private)}</span></button>}
      </div>}</section>
    </aside>

    <section className="catalog-content" aria-label="模型广场">
      <div className="catalog-toolbar"><label className="catalog-search"><Search size={16} /><input aria-label="搜索模型名称" placeholder="搜索模型名称" value={search} onChange={event => setSearch(event.target.value)} />{search && <button type="button" aria-label="清除搜索" title="清除搜索" onClick={() => setSearch('')}><X size={15} /></button>}</label><div className="catalog-count"><strong>{visible.length}</strong> 个模型</div><div className="catalog-toolbar-controls">
        <div className="catalog-segment" aria-label="排序"><button type="button" className={sortBy === 'name' ? 'active' : ''} onClick={() => changeSort('name')}>名称 {sortBy === 'name' && (ascending ? '↑' : '↓')}</button><button type="button" className={sortBy === 'price' ? 'active' : ''} onClick={() => changeSort('price')}>价格 {sortBy === 'price' && (ascending ? '↑' : '↓')}</button></div>
        <div className="catalog-segment" aria-label="视图"><button type="button" className={view === 'grid' ? 'active' : ''} onClick={() => setView('grid')} title="网格视图" aria-label="网格视图"><Grid2X2 size={16} /></button><button type="button" className={view === 'list' ? 'active' : ''} onClick={() => setView('list')} title="列表视图" aria-label="列表视图"><List size={16} /></button></div>
      </div></div>
      {error && <Notice text={error} error />}
      {loading ? <div className="catalog-loading">正在加载模型...</div> : visible.length ? <div className={`catalog-grid ${view === 'list' ? 'catalog-list-view' : ''}`}>{visible.map(item => <article className="catalog-card" key={`${item.group_id}-${item.name}`}>
        <div className="catalog-card-top"><span className="catalog-model-icon"><Store size={22} /></span><div className="catalog-card-name"><strong>{item.name}</strong><span>{priceLabel(item)}</span></div><button type="button" className="catalog-detail-button" onClick={() => setSelected(item)}>详情 <ChevronRight size={14} /></button><button type="button" className="catalog-copy-button" title={copiedName === item.name ? '已复制' : '复制模型名称'} aria-label={`${copiedName === item.name ? '已复制' : '复制'} ${item.name} 模型名称`} onClick={() => copyName(item.name)}>{copiedName === item.name ? <Check size={15} /> : <Copy size={15} />}</button></div>
        <p className="catalog-card-description">{item.billing_mode === 'anlas' ? '按实际 Anlas 消耗计费' : '按每次生成计费'}</p>
        <div className="catalog-card-bottom"><div><strong>{item.group_name}</strong><span className={`catalog-billing-tag ${item.billing_mode === 'fixed' ? 'fixed' : ''}`}>{item.billing_mode === 'anlas' ? '按 Anlas' : '按次计费'}</span></div><small>{item.is_private ? '专属分组' : '公开分组'}</small></div>
      </article>)}</div> : !error && <Empty text="当前筛选下暂无模型" />}
    </section>

    {selected && <div className="dialog-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) setSelected(null) }}><section className="dialog-panel catalog-detail" role="dialog" aria-modal="true" aria-label={`${selected.name} 详情`}>
      <div className="dialog-heading"><h2>{selected.name}</h2><button type="button" className="icon-button" aria-label="关闭详情" title="关闭详情" onClick={() => setSelected(null)}><X size={19} /></button></div>
      <dl className="detail-grid"><dt>所属分组</dt><dd>{selected.group_name}（{selected.is_private ? '专属' : '公开'}）</dd><dt>计费方式</dt><dd>{selected.billing_mode === 'anlas' ? '按 Anlas' : '按次'}</dd><dt>单价</dt><dd>{priceLabel(selected)}</dd>{selected.billing_mode === 'anlas' && Number(selected.extra_amount) > 0 && <><dt>每次附加费</dt><dd>{formatMoney(selected.extra_amount)}</dd></>}</dl>
      <button type="button" className="button secondary catalog-detail-copy" onClick={() => copyName(selected.name)}>{copiedName === selected.name ? <Check size={15} /> : <Copy size={15} />}{copiedName === selected.name ? '已复制' : '复制模型名称'}</button>
    </section></div>}
  </div>
}
