import { execFileSync } from 'node:child_process'
import { writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const config = JSON.parse(execFileSync('python', ['-c',
  'import json,sys,yaml; print(json.dumps(yaml.safe_load(open(sys.argv[1],encoding="utf-8"))))',
  join(root, 'config.yaml')], { encoding: 'utf8' }))
const tabs = await (await fetch('http://127.0.0.1:9222/json/list')).json()
const tab = tabs.find(item => item.url.startsWith('http://127.0.0.1:8009/'))
if (!tab) throw new Error('Open a local page in Edge with CDP port 9222 first')
const socket = new WebSocket(tab.webSocketDebuggerUrl)
await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject })
let nextId = 1
const pending = new Map()
const exceptions = []
socket.onmessage = event => {
  const message = JSON.parse(event.data)
  if (message.method === 'Runtime.exceptionThrown') exceptions.push(message.params.exceptionDetails.exception?.description)
  if (message.id && pending.has(message.id)) {
    const { resolve, reject } = pending.get(message.id)
    pending.delete(message.id)
    message.error ? reject(new Error(message.error.message)) : resolve(message.result)
  }
}
const command = (method, params = {}) => new Promise((resolve, reject) => {
  const id = nextId++
  pending.set(id, { resolve, reject })
  socket.send(JSON.stringify({ id, method, params }))
})
const evaluate = async expression => {
  const result = await command('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true })
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.text)
  return result.result.value
}
const pause = ms => new Promise(resolve => setTimeout(resolve, ms))
const screenshot = async name => {
  const result = await command('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })
  writeFileSync(join(root, 'data', name), Buffer.from(result.data, 'base64'))
}

await command('Runtime.enable')
await command('Page.enable')
exceptions.length = 0
const login = await evaluate(`fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(${JSON.stringify({ email: config.admin.email, password: config.admin.password })})}).then(r=>r.status)`)
if (login !== 200) throw new Error(`Browser login returned ${login}`)
await command('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false })
await command('Page.navigate', { url: 'http://127.0.0.1:8009/workshop' })
await pause(3000)
console.log('workshop', await evaluate('document.body.innerText.slice(0,260)'))
await screenshot('workshop-desktop.png')
await command('Page.navigate', { url: 'http://127.0.0.1:8009/' })
await pause(1200)
await screenshot('dashboard-desktop.png')
for (const [path, name] of [['keys', 'keys-desktop.png'], ['jobs', 'usage-desktop.png'],
  ['billing', 'billing-desktop.png'], ['admin', 'admin-desktop.png']]) {
  await command('Page.navigate', { url: `http://127.0.0.1:8009/${path}` })
  await pause(1200)
  await screenshot(name)
}
await command('Page.navigate', { url: 'http://127.0.0.1:8009/workshop' })
await pause(1200)
await command('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true })
await pause(1000)
await screenshot('workshop-mobile.png')
console.log('mobile logout visible', await evaluate('Boolean(document.querySelector(".mobile-account .icon-button"))'))
await evaluate('document.querySelector(".mobile-account .icon-button").click()')
await pause(1200)
console.log('after logout', await evaluate('({path:location.pathname,login:document.body.innerText.includes("欢迎回来")})'))
await screenshot('logout-mobile.png')
console.log('browser exceptions', exceptions)
socket.close()
