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
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text)
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
await evaluate(`[...document.querySelectorAll('.tab')].find(button => button.textContent === '分组').click()`)
await pause(250)
const groupsTab = await evaluate(`(() => {
  const scope = [...document.querySelectorAll('label')].find(label => label.textContent.startsWith('可见范围'))?.querySelector('select')
  const defaultPublic = scope?.value === 'public'
  scope.value = 'private'
  scope.dispatchEvent(new Event('change', { bubbles: true }))
  return defaultPublic
})()`)
await pause(250)
const privateControls = await evaluate(`({
  recipients:document.querySelectorAll('.form-grid .wide input[type="checkbox"]').length,
  saveDisabled:[...document.querySelectorAll('.form-grid button')].find(button => button.textContent.includes('保存分组'))?.disabled
})`)
if (!groupsTab || !privateControls.recipients || !privateControls.saveDisabled) throw new Error(`Private group controls: ${JSON.stringify(privateControls)}`)
await evaluate(`[...document.querySelectorAll('.tab')].find(button => button.textContent === '模型与定价').click()`)
await pause(250)
const backupLimit = await evaluate(`(() => {
  const group = [...document.querySelectorAll('label')].find(label => label.textContent.startsWith('分组'))?.querySelector('select')
  group.value = group.options[1]?.value || ''
  group.dispatchEvent(new Event('change', { bubbles: true }))
  return Boolean(group.value)
})()`)
await pause(250)
const routeControl = await evaluate(`(() => {
  const primary = [...document.querySelectorAll('label')].find(label => label.textContent.startsWith('首选上游账户'))?.querySelector('select')
  primary.value = primary.options[1]?.value || ''
  primary.dispatchEvent(new Event('change', { bubbles: true }))
  return primary.options.length
})()`)
await pause(250)
const backupButton = await evaluate(`(() => {
  const button = [...document.querySelectorAll('button')].find(button => button.textContent.includes('添加备用账号'))
  const before = button.disabled
  return { before }
})()`)
if (!backupLimit || routeControl < 3 || backupButton.before) throw new Error(`Backup route controls: ${JSON.stringify({ backupLimit, routeControl, backupButton })}`)
for (let index = 0; index < routeControl - 2; index++) {
  await evaluate(`[...document.querySelectorAll('button')].find(button => button.textContent.includes('添加备用账号')).click()`)
  await pause(150)
}
const backupFull = await evaluate(`[...document.querySelectorAll('button')].find(button => button.textContent.includes('添加备用账号')).disabled`)
if (!backupFull) throw new Error('Backup route button remained enabled at the account limit')
await command('Page.navigate', { url: 'http://127.0.0.1:8009/workshop' })
await pause(1200)
const historyControls = await evaluate(`(() => {
  const row = document.querySelector('.studio-history-item')
  const controls = ['查看大图', '下载图片', '删除记录'].every(title => row?.querySelector('[title="' + title + '"]'))
  row?.querySelector('button[title="查看大图"]')?.click()
  return { controls }
})()`)
await pause(250)
const lightbox = await evaluate(`Boolean(document.querySelector('.studio-lightbox'))`)
if (!historyControls.controls || !lightbox) throw new Error(`Image history controls: ${JSON.stringify({ historyControls, lightbox })}`)
await screenshot('workshop-large-image.png')
await evaluate(`document.querySelector('.studio-lightbox button[title="关闭"]').click()`)
console.log('new controls', { privateControls, backupFull, historyControls, lightbox })
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
