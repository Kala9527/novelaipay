import { useEffect, useState, type FormEvent } from 'react'
import { Copy, KeyRound, Plus, Trash2 } from 'lucide-react'
import { api, formatDate, post } from '../lib/api'
import type { Group, Key } from '../types'
import { Empty, Notice, PageHeader } from '../components/UI'
import { usePreferences } from '../lib/preferences'

export function KeysPage() {
  const { t } = usePreferences()
  const [keys, setKeys] = useState<Key[]>([])
  const [groups, setGroups] = useState<Group[]>([])
  const [groupId, setGroupId] = useState('')
  const [name, setName] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const load = () => api<Key[]>('/api/keys').then(setKeys).catch(e => setError(e.message))
  useEffect(() => { load(); api<Group[]>('/api/groups').then(rows => { setGroups(rows); if (rows.length) setGroupId(String(rows[0].id)) }).catch(e => setError(e.message)) }, [])
  async function create(event: FormEvent) {
    event.preventDefault(); setError(''); setMessage('')
    try { await post<Key>('/api/keys', { name, group_id: Number(groupId) }); setName(''); setMessage(t('keyCreated')); load() }
    catch (e) { setError((e as Error).message) }
  }
  async function copy(id: number) {
    setError(''); setMessage('')
    try {
      const secret = await api<{ key: string }>(`/api/keys/${id}/secret`)
      await navigator.clipboard.writeText(secret.key)
      setMessage(t('keyCopied'))
    } catch (e) { setError((e as Error).message) }
  }
  async function revoke(id: number) {
    if (!window.confirm(t('revokeConfirm'))) return
    try { await api(`/api/keys/${id}`, { method: 'DELETE' }); load() }
    catch (e) { setError((e as Error).message) }
  }
  return <div className="page"><PageHeader title={t('keys')} subtitle={t('keySubtitle')} /><form className="inline-form" onSubmit={create}><label className="grow">{t('keyName')}<input value={name} maxLength={80} required placeholder={t('keyExample')} onChange={e => setName(e.target.value)} /></label><label>{t('group')}<select required value={groupId} onChange={e => setGroupId(e.target.value)}><option value="">{t('selectGroup')}</option>{groups.map(group => <option key={group.id} value={group.id}>{group.name}</option>)}</select></label><button className="button primary" disabled={!groupId}><Plus size={17} />{t('createKey')}</button></form>{error && <Notice text={error} error />}{message && <Notice text={message} />}<div className="section-head"><h2>{t('activeKeys')}</h2><span className="muted">{t('keyCount', { count: keys.length })}</span></div>{keys.length ? <div className="table-scroll"><table><thead><tr><th>{t('name')}</th><th>{t('group')}</th><th>{t('keys')}</th><th>{t('createdAt')}</th><th></th></tr></thead><tbody>{keys.map(key => <tr key={key.id}><td><span className="cell-icon"><KeyRound size={16} /></span>{key.name}</td><td>{groups.find(group => group.id === key.group_id)?.name || '-'}</td><td className="mono">{key.prefix}••••</td><td>{formatDate(key.created_at)}</td><td className="right"><div className="row-actions"><button className="icon-button" aria-label={key.can_copy ? t('copyKey') : t('oldKey')} title={key.can_copy ? t('copyKey') : t('oldKey')} disabled={!key.can_copy} onClick={() => copy(key.id)}><Copy size={17} /></button><button className="icon-button danger" aria-label={t('revokeKey')} title={t('revokeKey')} onClick={() => revoke(key.id)}><Trash2 size={17} /></button></div></td></tr>)}</tbody></table></div> : <Empty text={t('noKeys')} />}</div>
}
