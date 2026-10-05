import { useEffect, useState, type FormEvent } from 'react'
import { Copy, KeyRound, Plus, Trash2 } from 'lucide-react'
import { api, formatDate, formatMoney, post } from '../lib/api'
import type { AdminUser, Group, Key } from '../types'
import { Empty, Notice } from './UI'

export function UserManagement() {
  const [users, setUsers] = useState<AdminUser[]>([])
  const [groups, setGroups] = useState<Group[]>([])
  const [showDeleted, setShowDeleted] = useState(false)
  const [newUser, setNewUser] = useState({ name: '', email: '', password: '' })
  const [credit, setCredit] = useState({ user_id: '', amount: '', reference: '' })
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [keys, setKeys] = useState<Key[]>([])
  const [keyName, setKeyName] = useState('')
  const [keyGroupId, setKeyGroupId] = useState('')
  const [editing, setEditing] = useState<{ id: number; name: string } | null>(null)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  function loadUsers() { api<AdminUser[]>(`/api/admin/users?include_deleted=${showDeleted}`).then(setUsers).catch(e => setError(e.message)) }
  function loadKeys(id: number) { api<Key[]>(`/api/admin/users/${id}/keys`).then(setKeys).catch(e => setError(e.message)) }
  useEffect(() => { loadUsers() }, [showDeleted])
  useEffect(() => { api<Group[]>('/api/admin/groups').then(rows => { setGroups(rows); if (rows.length) setKeyGroupId(String(rows[0].id)) }).catch(e => setError(e.message)) }, [])

  async function run(action: () => Promise<unknown>, success = '操作成功', refreshKeys = true) {
    setError(''); setMessage('')
    try { await action(); setMessage(success); loadUsers(); if (selectedId && refreshKeys) loadKeys(selectedId); return true }
    catch (e) { setError((e as Error).message); return false }
  }

  async function create(event: FormEvent) {
    event.preventDefault()
    if (await run(() => post('/api/admin/users', newUser))) {
      setNewUser({ name: '', email: '', password: '' })
    }
  }

  async function addCredit(event: FormEvent) {
    event.preventDefault()
    if (await run(() => post('/api/admin/credit', { ...credit, user_id: Number(credit.user_id) }))) {
      setCredit({ user_id: '', amount: '', reference: '' })
    }
  }

  async function updateUser(event: FormEvent) {
    event.preventDefault()
    if (!editing) return
    if (await run(() => api(`/api/admin/users/${editing.id}`, {
      method: 'PATCH', body: JSON.stringify({ name: editing.name }),
    }))) setEditing(null)
  }

  async function toggle(user: AdminUser) {
    await run(() => api(`/api/admin/users/${user.id}`, {
      method: 'PATCH', body: JSON.stringify({ is_active: !user.is_active }),
    }), user.is_active ? '用户已禁用' : '用户已启用')
  }

  async function restore(user: AdminUser) {
    await run(() => api(`/api/admin/users/${user.id}`, {
      method: 'PATCH', body: JSON.stringify({ is_active: true }),
    }), '用户已恢复，请重新签发密钥')
  }

  async function remove(user: AdminUser) {
    if (!window.confirm(`删除 ${user.name || user.email}？历史账单会保留，操作后该账户无法登录。`)) return
    if (await run(() => api(`/api/admin/users/${user.id}`, { method: 'DELETE' }), '用户已删除', false)) {
      if (selectedId === user.id) { setSelectedId(null); setKeys([]) }
    }
  }

  async function issue(event: FormEvent) {
    event.preventDefault()
    if (!selectedId) return
    setError(''); setMessage('')
    try {
      await post<Key>(`/api/admin/users/${selectedId}/keys`, { name: keyName, group_id: Number(keyGroupId) })
      setKeyName('')
      setMessage('密钥已签发，可在下方复制。')
      loadKeys(selectedId)
    } catch (e) { setError((e as Error).message) }
  }

  async function revoke(keyId: number) {
    if (!selectedId || !window.confirm('撤销此密钥？')) return
    await run(() => api(`/api/admin/users/${selectedId}/keys/${keyId}`, { method: 'DELETE' }), '密钥已撤销')
  }

  async function copy(keyId: number) {
    if (!selectedId) return
    setError(''); setMessage('')
    try {
      const secret = await api<{ key: string }>(`/api/admin/users/${selectedId}/keys/${keyId}/secret`)
      await navigator.clipboard.writeText(secret.key)
      setMessage('密钥已复制到剪贴板')
    } catch (e) { setError((e as Error).message) }
  }

  const selected = users.find(user => user.id === selectedId)
  return <div>
    {error && <Notice text={error} error />}{message && <Notice text={message} />}
    <div className="section-head"><h2>创建普通用户</h2></div>
    <form className="form-grid" onSubmit={create}>
      <label>名称<input required maxLength={80} value={newUser.name} onChange={e => setNewUser({ ...newUser, name: e.target.value })} /></label>
      <label>邮箱<input required type="email" value={newUser.email} onChange={e => setNewUser({ ...newUser, email: e.target.value })} /></label>
      <label>初始密码<input required type="password" minLength={12} autoComplete="new-password" value={newUser.password} onChange={e => setNewUser({ ...newUser, password: e.target.value })} /></label>
      <button className="button primary"><Plus size={16} />创建用户</button>
    </form>

    <div className="section-head"><h2>账户入账</h2></div>
    <form className="form-grid" onSubmit={addCredit}>
      <label>用户<select required value={credit.user_id} onChange={e => setCredit({ ...credit, user_id: e.target.value })}><option value="">选择用户</option>{users.filter(u => u.is_active && !u.deleted_at).map(u => <option key={u.id} value={u.id}>{u.name || u.email}{u.is_admin ? '（管理员）' : ''}</option>)}</select></label>
      <label>金额 (CNY)<input required type="number" step="0.0001" min="0.0001" value={credit.amount} onChange={e => setCredit({ ...credit, amount: e.target.value })} /></label>
      <label>唯一流水号<input required maxLength={80} value={credit.reference} onChange={e => setCredit({ ...credit, reference: e.target.value })} /></label>
      <button className="button primary"><Plus size={16} />确认入账</button>
    </form>

    <div className="section-head"><h2>用户列表</h2><label className="check-label"><input type="checkbox" checked={showDeleted} onChange={e => setShowDeleted(e.target.checked)} />显示已删除</label></div>
    {users.length ? <div className="table-scroll"><table><thead><tr><th>用户</th><th>角色</th><th>状态</th><th>余额</th><th>预留</th><th>操作</th></tr></thead><tbody>{users.map(user => <tr key={user.id}>
      <td><strong>{user.name || user.email}</strong><div className="muted">{user.email}</div></td><td>{user.is_admin ? '管理员' : '普通用户'}</td><td>{user.deleted_at ? '已删除' : user.is_active ? '启用' : '禁用'}</td><td>{formatMoney(user.balance)}</td><td>{formatMoney(user.reserved)}</td>
      <td><div className="row-actions">{user.deleted_at ? <button className="text-link" onClick={() => restore(user)}>恢复</button> : <>{!user.is_admin && <><button className="text-link" onClick={() => setEditing({ id: user.id, name: user.name })}>编辑</button><button className="text-link" onClick={() => toggle(user)}>{user.is_active ? '禁用' : '启用'}</button><button className="text-link danger-text" onClick={() => remove(user)}>删除</button></>}<button className="text-link" onClick={() => { setSelectedId(user.id); loadKeys(user.id) }}>密钥</button></>}</div></td>
    </tr>)}</tbody></table></div> : <Empty text="暂无用户" />}

    {editing && <form className="form-grid edit-band" onSubmit={updateUser}><label>名称<input required value={editing.name} onChange={e => setEditing({ ...editing, name: e.target.value })} /></label><div className="button-group"><button className="button primary">保存</button><button type="button" className="button secondary" onClick={() => setEditing(null)}>取消</button></div></form>}

    {selected && <div className="key-management"><div className="section-head"><h2>{selected.name || selected.email} 的密钥</h2><button className="text-link" onClick={() => setSelectedId(null)}>关闭</button></div><form className="inline-form" onSubmit={issue}><label className="grow">密钥名称<input required maxLength={80} value={keyName} onChange={e => setKeyName(e.target.value)} placeholder="例如：业务系统 A" /></label><label>分组<select required value={keyGroupId} onChange={e => setKeyGroupId(e.target.value)}><option value="">选择分组</option>{groups.filter(group => group.enabled).map(group => <option key={group.id} value={group.id}>{group.name}</option>)}</select></label><button className="button primary" disabled={!selected.is_active || !keyGroupId}><Plus size={16} />签发密钥</button></form>{keys.length ? <div className="table-scroll key-table"><table><thead><tr><th>名称</th><th>分组</th><th>密钥</th><th>创建时间</th><th></th></tr></thead><tbody>{keys.map(key => <tr key={key.id}><td><KeyRound size={15} className="inline-icon" />{key.name}</td><td>{groups.find(group => group.id === key.group_id)?.name || '-'}</td><td className="mono">{key.prefix}••••</td><td>{formatDate(key.created_at)}</td><td className="right"><div className="row-actions"><button className="icon-button" title={key.can_copy ? '复制密钥' : '旧密钥无法恢复，请重新创建'} disabled={!key.can_copy} onClick={() => copy(key.id)}><Copy size={16} /></button><button className="icon-button danger" title="撤销密钥" onClick={() => revoke(key.id)}><Trash2 size={16} /></button></div></td></tr>)}</tbody></table></div> : <Empty text="暂无有效密钥" />}</div>}
  </div>
}
