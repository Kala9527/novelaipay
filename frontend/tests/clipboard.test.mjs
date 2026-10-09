import assert from 'node:assert/strict'
import { afterEach, test } from 'node:test'
import { copyText } from '../src/lib/clipboard.ts'

const originalClipboard = Object.getOwnPropertyDescriptor(navigator, 'clipboard')
const originalDocument = globalThis.document
const originalHTMLElement = globalThis.HTMLElement

afterEach(() => {
  if (originalClipboard) Object.defineProperty(navigator, 'clipboard', originalClipboard)
  else delete navigator.clipboard
  globalThis.document = originalDocument
  globalThis.HTMLElement = originalHTMLElement
})

function setClipboard(clipboard) {
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: clipboard })
}

function mockDocument(copyResult) {
  const calls = []
  class Element {
    focus() { calls.push('restore focus') }
  }
  const field = {
    value: '', readOnly: false, style: {},
    focus() { calls.push('field focus') },
    select() { calls.push('select') },
    remove() { calls.push('remove') },
  }
  globalThis.HTMLElement = Element
  globalThis.document = {
    activeElement: new Element(),
    createElement(tag) { assert.equal(tag, 'textarea'); return field },
    body: { append(element) { assert.equal(element, field); calls.push('append') } },
    execCommand(command) { assert.equal(command, 'copy'); calls.push('copy'); return copyResult },
  }
  return { field, calls }
}

test('uses the Clipboard API when available', async () => {
  const written = []
  setClipboard({ writeText: async value => written.push(value) })
  await copyText('pst-secret')
  assert.deepEqual(written, ['pst-secret'])
})

test('copies through the selection fallback on HTTP pages', async () => {
  setClipboard(undefined)
  const { field, calls } = mockDocument(true)
  await copyText('pst-secret')
  assert.equal(field.value, 'pst-secret')
  assert.equal(field.readOnly, true)
  assert.deepEqual(calls, ['append', 'field focus', 'select', 'copy', 'remove', 'restore focus'])
})

test('falls back when the Clipboard API rejects', async () => {
  setClipboard({ writeText: async () => { throw new Error('denied') } })
  const { calls } = mockDocument(true)
  await copyText('pst-secret')
  assert.ok(calls.includes('copy'))
})

test('reports failure and removes the temporary field', async () => {
  setClipboard(undefined)
  const { calls } = mockDocument(false)
  await assert.rejects(copyText('pst-secret'), /Clipboard copy is unavailable/)
  assert.deepEqual(calls.slice(-2), ['remove', 'restore focus'])
})
