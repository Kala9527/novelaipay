import { writeFileSync, mkdirSync } from 'node:fs'
import { resolve } from 'node:path'

const base = process.env.PREVIEW_URL || 'http://127.0.0.1:8010'
const debuggerBase = process.env.CDP_URL || 'http://127.0.0.1:9222'
const tab = await (await fetch(`${debuggerBase}/json/new?${encodeURIComponent(base)}`, { method: 'PUT' })).json()
const socket = new WebSocket(tab.webSocketDebuggerUrl)
await new Promise((done, fail) => { socket.onopen = done; socket.onerror = fail })
let serial = 0
const pending = new Map()
const exceptions = []
socket.onmessage = event => {
  const message = JSON.parse(event.data)
  if (message.method === 'Runtime.exceptionThrown') exceptions.push(message.params.exceptionDetails.text)
  if (pending.has(message.id)) {
    const { done, fail } = pending.get(message.id)
    pending.delete(message.id)
    message.error ? fail(new Error(message.error.message)) : done(message.result)
  }
}
const command = (method, params = {}) => new Promise((done, fail) => {
  const id = ++serial
  pending.set(id, { done, fail })
  socket.send(JSON.stringify({ id, method, params }))
})
const evaluate = async expression => {
  const result = await command('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true })
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.text)
  return result.result.value
}
const wait = ms => new Promise(done => setTimeout(done, ms))
const navigate = async path => { await command('Page.navigate', { url: base + path }); await wait(700) }
const screenshot = async name => {
  const file = resolve('backend/data', name)
  mkdirSync(resolve('backend/data'), { recursive: true })
  const result = await command('Page.captureScreenshot', { format: 'png' })
  writeFileSync(file, Buffer.from(result.data, 'base64'))
}
try {
  await command('Page.enable')
  await command('Runtime.enable')
  await navigate('/login')
  const login = await evaluate(`fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:${JSON.stringify(process.env.PREVIEW_EMAIL)},password:${JSON.stringify(process.env.PREVIEW_PASSWORD)}})}).then(r=>r.status)`)
  if (login !== 200) throw new Error(`Login returned ${login}`)
  await command('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false })
  await navigate('/admin')
  const admin = await evaluate('({title:document.querySelector("h1")?.innerText,groups:document.body.innerText.includes("分组"),error:document.body.innerText.includes("请求失败")})')
  if (admin.title !== '管理设置' || !admin.groups || admin.error) throw new Error(`Admin page: ${JSON.stringify(admin)}`)
  await screenshot('preview-admin-desktop.png')
  await navigate('/keys')
  const keys = await evaluate('document.body.innerText.includes("选择分组")')
  if (!keys) throw new Error('Key group selector missing')
  await navigate('/billing')
  const billing = await evaluate('document.body.innerText.includes("开始日期 (北京时间)") && document.body.innerText.includes("全部用户")')
  if (!billing) throw new Error('Billing filters missing')
  await command('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true })
  await navigate('/admin')
  const mobile = await evaluate('({width:document.documentElement.scrollWidth,viewport:innerWidth,title:document.querySelector("h1")?.innerText})')
  await screenshot('preview-admin-mobile.png')
  if (mobile.width > mobile.viewport + 2) throw new Error(`Mobile horizontal overflow: ${JSON.stringify(mobile)}`)
  if (exceptions.length) throw new Error(`Browser exceptions: ${exceptions.join('; ')}`)
  console.log(JSON.stringify({ admin, keys, billing, mobile, exceptions }))
} finally {
  socket.close()
  await fetch(`${debuggerBase}/json/close/${tab.id}`)
}
