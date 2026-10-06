import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, BookOpen, Check, Copy, KeyRound, Store, WandSparkles } from 'lucide-react'
import { PageHeader } from '../components/UI'
import { usePreferences } from '../lib/preferences'

export function QuickstartPage() {
  const { t } = usePreferences()
  const [copied, setCopied] = useState(false)
  async function copy() {
    try { await navigator.clipboard.writeText(window.location.origin); setCopied(true); window.setTimeout(() => setCopied(false), 1800) } catch { setCopied(false) }
  }
  const steps = [
    { number: '01', icon: KeyRound, title: t('setupStep1'), body: t('setupStep1Body'), to: '/keys', action: t('openKeys') },
    { number: '02', icon: Store, title: t('setupStep2'), body: t('setupStep2Body'), to: '/models', action: t('browseModels') },
    { number: '03', icon: WandSparkles, title: t('setupStep3'), body: t('setupStep3Body'), to: '/workshop', action: t('openStudio') },
  ]
  return <div className="page quickstart-page">
    <PageHeader title={t('setupTitle')} subtitle={t('setupSubtitle')} />
    <div className="setup-steps">{steps.map(({ number, icon: Icon, title, body, to, action }) => <section className="setup-step" key={number}>
      <div className="setup-step-heading"><span>{number}</span><Icon size={21} /></div><h2>{title}</h2><p>{body}</p><Link className="text-link" to={to}>{action}<ArrowRight size={16} /></Link>
    </section>)}</div>
    <div className="setup-connection"><div><span className="section-eyebrow">API</span><h2>{t('serviceAddress')}</h2><code>{window.location.origin}</code></div><button type="button" className="button secondary" onClick={copy}>{copied ? <Check size={16} /> : <Copy size={16} />}{copied ? t('copied') : t('copyAddress')}</button></div>
    <Link className="button secondary setup-docs" to="/api-guide"><BookOpen size={16} />{t('readDocs')}<ArrowRight size={16} /></Link>
  </div>
}
