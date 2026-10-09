import assert from 'node:assert/strict'
import { test } from 'node:test'
import { newIdempotencyKey } from '../src/lib/idempotency.ts'

test('generates distinct 128-bit idempotency keys without randomUUID', () => {
  const keys = Array.from({ length: 100 }, newIdempotencyKey)
  assert.equal(new Set(keys).size, keys.length)
  for (const key of keys) assert.match(key, /^[0-9a-f]{32}$/)
})
