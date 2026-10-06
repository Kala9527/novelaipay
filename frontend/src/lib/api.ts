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
  if (options.method && options.method.toUpperCase() !== 'GET') window.dispatchEvent(new Event('novelaipay:data-changed'))
  return body as T
}

export const post = <T>(path: string, data: unknown) => api<T>(path, { method: 'POST', body: JSON.stringify(data) })

export async function downloadCsv(path: string, filename: string) {
  const headers = new Headers()
  if (csrfToken()) headers.set('X-CSRF-Token', csrfToken())
  const response = await fetch(path, { headers, credentials: 'same-origin' })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(typeof body.detail === 'string' ? body.detail : `导出失败 (${response.status})`)
  }
  const url = URL.createObjectURL(await response.blob())
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.append(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}
export const formatMoney = (value: string | number) => `¥${Number(value).toFixed(2)}`
export const formatDate = (value: string) => new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`).toLocaleString(document.documentElement.lang || 'zh-CN', { timeZone: 'Asia/Shanghai', hour12: false })
export const beijingInput = (value: string | null) => value ? new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`).toLocaleString('sv-SE', { timeZone: 'Asia/Shanghai', hour12: false }).slice(0, 16).replace(' ', 'T') : ''
export const beijingToUtc = (value: string) => value ? new Date(`${value}+08:00`).toISOString() : null
