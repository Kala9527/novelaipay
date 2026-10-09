import { useEffect, useState, type FormEvent } from 'react'
import { Check, ChevronLeft, ChevronRight, Copy, KeyRound, LockKeyhole, Pencil, Plus, RotateCcw, Search, Trash2, X } from 'lucide-react'
import { api, formatDate, formatMoney, post } from '../lib/api'
import { copyText } from '../lib/clipboard'
import type { AdminUser, Group, Key } from '../types'
import { Empty, Notice } from './UI'

export function UserManagement() {
  const [users, setUsers] = useState<AdminUser[]>([])
  const [groups, setGroups] = useState<Group[]>([])
  const [showDeleted, setShowDeleted] = useState(false)
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(0)
  const [panel, setPanel] = useState<'create' | 'credit' | null>(null)
  const [newUser, setNewUser] = useState({ name: '', email: '', password: '', max_concurrency: 2 })
  const [credit, setCredit] = useState({ user_id: '', amount: '' })
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [keys, setKeys] = useState<Key[]>([])
  const [keyName, setKeyName] = useState('')
  const [keyGroupId, setKeyGroupId] = useState('')
  const [editing, setEditing] = useState<{ id: number; name: string; email: string; max_concurrency: number } | null>(null)
  const [reset, setReset] = useState<{ id: number; name: string; password: string; confirm: string } | null>(null)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [manualKey, setManualKey] = useState('')
  useEffect(() => { setManualKey('') }, [selectedId])

  function loadUsers() { api<AdminUser[]>(`/api/admin/users?include_deleted=${showDeleted}&search=${encodeURIComponent(search)}&offset=${page * 50}&limit=50`).then(setUsers).catch(e => setError(e.message)) }
  function loadKeys(id: number) { api<Key[]>(`/api/admin/users/${id}/keys`).then(setKeys).catch(e => setError(e.message)) }
  useEffect(() => {
    let current = true
    api<AdminUser[]>(`/api/admin/users?include_deleted=${showDeleted}&search=${encodeURIComponent(search)}&offset=${page * 50}&limit=50`)
      .then(rows => { if (current) setUsers(rows) })
      .catch(e => { if (current) setError(e.message) })
    return () => { current = false }
  }, [showDeleted, search, page])
  useEffect(() => {
    const interval = window.setInterval(loadUsers, 10000)
    window.addEventListener('novelaipay:data-changed', loadUsers)
    return () => { window.clearInterval(interval); window.removeEventListener('novelaipay:data-changed', loadUsers) }
  }, [showDeleted, search, page])
  useEffect(() => { api<Group[]>('/api/admin/groups').then(setGroups).catch(e => setError(e.message)) }, [])

  async function run(action: () => Promise<unknown>, success = '操作成功', refreshKeys = true) {
    setError(''); setMessage('')
    try { await action(); setMessage(success); loadUsers(); if (selectedId && refreshKeys) loadKeys(selectedId); return true }
    catch (e) { setError((e as Error).message); return false }
  }

  async function create(event: FormEvent) {
    event.preventDefault()
    if (await run(() => post('/api/admin/users', newUser))) {
      setNewUser({ name: '', email: '', password: '', max_concurrency: 2 }); setPanel(null)
    }
  }

  async function addCredit(event: FormEvent) {
    event.preventDefault()
    if (await run(() => post('/api/admin/credit', { ...credit, user_id: Number(credit.user_id) }))) {
      setCredit({ user_id: '', amount: '' }); setPanel(null)
    }
  }

  async function updateUser(event: FormEvent) {
    event.preventDefault()
    if (!editing) return
    if (await run(() => api(`/api/admin/users/${editing.id}`, {
      method: 'PATCH', body: JSON.stringify({ name: editing.name, email: editing.email,
        max_concurrency: editing.max_concurrency }),
    }))) setEditing(null)
  }

  async function resetPassword(event: FormEvent) {
    event.preventDefault()
    if (!reset) return
    if (reset.password !== reset.confirm) { setError('两次输入的密码不一致'); return }
    if (await run(() => post(`/api/admin/users/${reset.id}/reset-password`, { password: reset.password }), '密码已重置，原登录会话已失效')) setReset(null)
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
    setError(''); setMessage(''); setManualKey('')
    try {
      await post<Key>(`/api/admin/users/${selectedId}/keys`, { name: keyName, group_id: Number(keyGroupId) })
      setKeyName('')
      setMessage('密钥已签发，可在下方复制。')
      loadKeys(selectedId)
    } catch (e) { setError((e as Error).message) }
  }

  async function revoke(keyId: number) {
    if (!selectedId || !window.confirm('撤销此密钥？')) return
    setManualKey('')
    await run(() => api(`/api/admin/users/${selectedId}/keys/${keyId}`, { method: 'DELETE' }), '密钥已撤销')
  }

  async function copy(keyId: number) {
    if (!selectedId) return
    setError(''); setMessage(''); setManualKey('')
    try {
      const secret = await api<{ key: string }>(`/api/admin/users/${selectedId}/keys/${keyId}/secret`)
      try {
        await copyText(secret.key)
        setMessage('密钥已复制到剪贴板')
      } catch {
        setManualKey(secret.key)
        setError('浏览器无法自动复制，请选中下方密钥手动复制。')
      }
    } catch (e) { setError((e as Error).message) }
  }

  const selected = users.find(user => user.id === selectedId)
  const availableGroups = groups.filter(group => group.enabled && (!group.is_private || group.member_ids.includes(selectedId ?? -1)))
  const visibleUsers = users
  return <div>
    {error && <Notice text={error} error />}{message && <Notice text={message} />}{manualKey && <div className="secret-panel"><input aria-label="完整密钥" readOnly value={manualKey} onFocus={e => e.currentTarget.select()} /><button type="button" className="icon-button" title="关闭" onClick={() => setManualKey('')}><X size={17} /></button></div>}
    <div className="admin-toolbar"><div><h2>用户列表</h2><span>本页 {visibleUsers.length} 人</span></div><div className="admin-toolbar-actions"><label className="admin-search"><Search size={15} /><input aria-label="搜索用户" placeholder="搜索姓名或邮箱" value={search} onChange={e => { setSearch(e.target.value); setPage(0) }} /></label><label className="check-label"><input type="checkbox" checked={showDeleted} onChange={e => { setShowDeleted(e.target.checked); setPage(0) }} />显示已删除</label><button type="button" className="button secondary" onClick={() => { setPanel('credit'); setEditing(null) }}>账户入账</button><button type="button" className="button primary" onClick={() => { setPanel('create'); setEditing(null) }}><Plus size={16} />创建用户</button></div></div>
    {panel === 'create' && <section id="admin-editor" className="admin-edit-section"><div className="admin-edit-heading"><h3>创建普通用户</h3><button type="button" className="icon-button" title="关闭" onClick={() => setPanel(null)}><X size={17} /></button></div><form className="form-grid" onSubmit={create}>
      <label>名称<input required maxLength={80} value={newUser.name} onChange={e => setNewUser({ ...newUser, name: e.target.value })} /></label>
      <label>邮箱<input required type="email" value={newUser.email} onChange={e => setNewUser({ ...newUser, email: e.target.value })} /></label>
      <label>初始密码<input required type="password" minLength={12} autoComplete="new-password" value={newUser.password} onChange={e => setNewUser({ ...newUser, password: e.target.value })} /></label>
      <label>最大并发数<input required type="number" min="1" max="100" value={newUser.max_concurrency} onChange={e => setNewUser({ ...newUser, max_concurrency: Number(e.target.value) })} /></label>
      <div className="admin-form-actions"><button className="button primary"><Check size={16} />创建用户</button><button type="button" className="button secondary" onClick={() => setPanel(null)}>取消</button></div>
    </form></section>}

    {panel === 'credit' && <section id="admin-editor" className="admin-edit-section"><div className="admin-edit-heading"><h3>账户入账</h3><button type="button" className="icon-button" title="关闭" onClick={() => setPanel(null)}><X size={17} /></button></div><form className="form-grid" onSubmit={addCredit}>
      <label>用户<select required value={credit.user_id} onChange={e => setCredit({ ...credit, user_id: e.target.value })}><option value="">选择用户</option>{users.filter(u => u.is_active && !u.deleted_at).map(u => <option key={u.id} value={u.id}>{u.name || u.email}{u.is_admin ? '（管理员）' : ''}</option>)}</select></label>
      <label>金额 (CNY)<input required type="number" step="0.0001" min="0.0001" value={credit.amount} onChange={e => setCredit({ ...credit, amount: e.target.value })} /></label>
      <div className="admin-form-actions"><button className="button primary"><Check size={16} />确认入账</button><button type="button" className="button secondary" onClick={() => setPanel(null)}>取消</button></div>
    </form></section>}

    {editing && <section id="admin-editor" className="admin-edit-section"><div className="admin-edit-heading"><h3>编辑用户 · {editing.name}</h3><button type="button" className="icon-button" title="关闭" onClick={() => setEditing(null)}><X size={17} /></button></div><form className="form-grid" onSubmit={updateUser}><label>名称<input required value={editing.name} onChange={e => setEditing({ ...editing, name: e.target.value })} /></label><label>邮箱<input required type="email" value={editing.email} onChange={e => setEditing({ ...editing, email: e.target.value })} /></label><label>最大并发数<input required type="number" min="1" max="100" value={editing.max_concurrency} onChange={e => setEditing({ ...editing, max_concurrency: Number(e.target.value) })} /></label><div className="admin-form-actions"><button className="button primary"><Check size={16} />保存用户</button><button type="button" className="button secondary" onClick={() => setEditing(null)}>取消</button></div></form></section>}
    {reset && <section id="admin-editor" className="admin-edit-section"><div className="admin-edit-heading"><h3>重置密码 · {reset.name}</h3><button type="button" className="icon-button" title="关闭" onClick={() => setReset(null)}><X size={17} /></button></div><form className="form-grid" onSubmit={resetPassword}><label>新密码<input required type="password" autoComplete="new-password" minLength={12} maxLength={200} value={reset.password} onChange={e => setReset({ ...reset, password: e.target.value })} /></label><label>确认新密码<input required type="password" autoComplete="new-password" minLength={12} value={reset.confirm} onChange={e => setReset({ ...reset, confirm: e.target.value })} /></label><div className="admin-form-actions"><button className="button primary"><LockKeyhole size={16} />重置密码</button><button type="button" className="button secondary" onClick={() => setReset(null)}>取消</button></div></form></section>}
    {visibleUsers.length ? <div className="table-scroll admin-table"><table><thead><tr><th>用户</th><th>角色</th><th>状态</th><th>余额</th><th>预留</th><th className="right">操作</th></tr></thead><tbody>{visibleUsers.map(user => <tr key={user.id}>
      <td><strong>{user.name || user.email}</strong><div className="muted">{user.email}</div></td><td>{user.is_admin ? '管理员' : '普通用户'}</td><td>{user.deleted_at ? '已删除' : user.is_active ? '启用' : '禁用'}</td><td>{formatMoney(user.balance)}</td><td>{formatMoney(user.reserved)}</td>
      <td className="right"><div className="admin-row-actions">{user.deleted_at ? <button className="icon-button" title="恢复用户" onClick={() => restore(user)}><RotateCcw size={16} /></button> : <>{!user.is_admin && <><button className="icon-button" title="编辑用户" onClick={() => { setPanel(null); setReset(null); setEditing({ id: user.id, name: user.name, email: user.email, max_concurrency: user.max_concurrency }) }}><Pencil size={16} /></button><button className="icon-button" title="重置密码" onClick={() => { setPanel(null); setEditing(null); setReset({ id: user.id, name: user.name || user.email, password: '', confirm: '' }) }}><LockKeyhole size={16} /></button><button className="icon-button" title={user.is_active ? '禁用用户' : '启用用户'} onClick={() => toggle(user)}>{user.is_active ? <X size={16} /> : <Check size={16} />}</button><button className="icon-button danger" title="删除用户" onClick={() => remove(user)}><Trash2 size={16} /></button></>}<button className="icon-button" title="管理密钥" onClick={() => { setSelectedId(user.id); setKeyGroupId(''); loadKeys(user.id) }}><KeyRound size={16} /></button></>}</div></td>
    </tr>)}</tbody></table></div> : <Empty text="暂无用户" />}
    <div className="admin-pagination"><span>第 {page + 1} 页</span><button className="icon-button" title="上一页" disabled={page === 0} onClick={() => setPage(current => current - 1)}><ChevronLeft size={17} /></button><button className="icon-button" title="下一页" disabled={users.length < 50} onClick={() => setPage(current => current + 1)}><ChevronRight size={17} /></button></div>

    {selected && <div className="key-management"><div className="section-head"><h2>{selected.name || selected.email} 的密钥</h2><button className="text-link" onClick={() => setSelectedId(null)}>关闭</button></div><form className="inline-form" onSubmit={issue}><label className="grow">密钥名称<input required maxLength={80} value={keyName} onChange={e => setKeyName(e.target.value)} placeholder="例如：业务系统 A" /></label><label>分组<select required value={keyGroupId} onChange={e => setKeyGroupId(e.target.value)}><option value="">选择分组</option>{availableGroups.map(group => <option key={group.id} value={group.id}>{group.name}</option>)}</select></label><button className="button primary" disabled={!selected.is_active || !keyGroupId}><Plus size={16} />签发密钥</button></form>{keys.length ? <div className="table-scroll key-table"><table><thead><tr><th>名称</th><th>分组</th><th>密钥</th><th>创建时间</th><th></th></tr></thead><tbody>{keys.map(key => <tr key={key.id}><td><KeyRound size={15} className="inline-icon" />{key.name}</td><td>{groups.find(group => group.id === key.group_id)?.name || '-'}</td><td className="mono">{key.prefix}••••</td><td>{formatDate(key.created_at)}</td><td className="right"><div className="row-actions"><button className="icon-button" title={key.can_copy ? '复制密钥' : '旧密钥无法恢复，请重新创建'} disabled={!key.can_copy} onClick={() => copy(key.id)}><Copy size={16} /></button><button className="icon-button danger" title="撤销密钥" onClick={() => revoke(key.id)}><Trash2 size={16} /></button></div></td></tr>)}</tbody></table></div> : <Empty text="暂无有效密钥" />}</div>}
  </div>
}
