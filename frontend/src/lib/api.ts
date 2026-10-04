function csrfToken() {
  return document.cookie.split('; ').find(v => v.startsWith('nvp_csrf='))?.split('=')[1] || ''
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  if (options.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  if (csrfToken()) headers.set('X-CSRF-Token', csrfToken())
  const response = await fetch(path, { ...options, headers, credentials: 'same-origin' })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : `请求失败 (${response.status})`)
  return body as T
}

export const post = <T>(path: string, data: unknown) => api<T>(path, { method: 'POST', body: JSON.stringify(data) })
export const formatMoney = (value: string | number) => `¥${Number(value).toFixed(2)}`
export const formatDate = (value: string) => new Date(value).toLocaleString('zh-CN')
