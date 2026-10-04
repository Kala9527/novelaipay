import type { ReactNode } from 'react'
import { AlertCircle, CheckCircle2 } from 'lucide-react'

export function PageHeader({ title, subtitle, action }: { title: string; subtitle?: string; action?: ReactNode }) {
  return <div className="page-header"><div><h1>{title}</h1>{subtitle && <p>{subtitle}</p>}</div>{action}</div>
}

export function Notice({ text, error = false }: { text: string; error?: boolean }) {
  return <div className={error ? 'notice error' : 'notice'}>{error ? <AlertCircle size={17} /> : <CheckCircle2 size={17} />}{text}</div>
}

export function Empty({ text }: { text: string }) { return <div className="empty-state">{text}</div> }

export function Status({ value }: { value: string }) {
  const names: Record<string, string> = { queued: '排队中', running: '生成中', succeeded: '已完成', failed: '失败', uncertain: '待核对' }
  return <span className={`status status-${value}`}>{names[value] || value}</span>
}
