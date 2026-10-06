import { useState, type FormEvent } from 'react'
import { Gift } from 'lucide-react'
import { PageHeader, Notice } from '../components/UI'
import { formatMoney, post } from '../lib/api'

export function RedemptionPage() {
  const [code, setCode] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  async function redeem(event: FormEvent) {
    event.preventDefault()
    setBusy(true); setError(''); setMessage('')
    try {
      const result = await post<{ amount: string }>('/api/redemption-codes/redeem', { code: code.trim() })
      setMessage(`兑换成功，余额增加 ${formatMoney(result.amount)}`)
      setCode('')
    } catch (e) { setError((e as Error).message) }
    finally { setBusy(false) }
  }
  return <div className="page"><PageHeader title="兑换码" />
    {error && <Notice text={error} error />}{message && <Notice text={message} />}
    <form className="inline-form" onSubmit={redeem}><label className="grow">兑换码<input required value={code} onChange={e => setCode(e.target.value)} placeholder="NVP-..." autoComplete="off" /></label><button className="button primary" disabled={busy || !code.trim()}><Gift size={16} />兑换</button></form>
  </div>
}
