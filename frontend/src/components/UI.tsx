import type { ReactNode } from 'react'
import { AlertCircle, CheckCircle2 } from 'lucide-react'
import { usePreferences } from '../lib/preferences'

export function PageHeader({ title, subtitle, action }: { title: string; subtitle?: string; action?: ReactNode }) {
  return <div className="page-header"><div><h1>{title}</h1>{subtitle && <p>{subtitle}</p>}</div>{action}</div>
}

export function Notice({ text, error = false }: { text: string; error?: boolean }) {
  return <div className={error ? 'notice error' : 'notice'}>{error ? <AlertCircle size={17} /> : <CheckCircle2 size={17} />}{text}</div>
}

export function Empty({ text }: { text: string }) { return <div className="empty-state">{text}</div> }

export function Status({ value }: { value: string }) {
  const { t } = usePreferences()
  const names: Record<string, string> = { queued: t('queued'), running: t('running'), succeeded: t('succeeded'), failed: t('failed'), uncertain: t('uncertain') }
  return <span className={`status status-${value}`}>{names[value] || value}</span>
}
