import type { Job } from '../types'

export type CachedImage = { id: string; userId: number; model: string; prompt: string; createdAt: string; blob: Blob }

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open('novelaipay-images', 1)
    request.onupgradeneeded = () => request.result.createObjectStore('images', { keyPath: 'id' })
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

export async function recentImages(userId: number): Promise<CachedImage[]> {
  const db = await openDatabase()
  try {
    return await new Promise((resolve, reject) => {
      const request = db.transaction('images').objectStore('images').getAll()
      request.onsuccess = () => resolve((request.result as CachedImage[])
        .filter(image => image.userId === userId)
        .sort((a, b) => b.createdAt.localeCompare(a.createdAt)).slice(0, 5))
      request.onerror = () => reject(request.error)
    })
  } finally { db.close() }
}

export async function saveImage(userId: number, job: Job): Promise<void> {
  const imageUrl = job.result?.data?.[0]?.url
  if (!imageUrl) return
  const existing = await recentImages(userId)
  if (existing.some(image => image.id === job.id)) return
  const response = await fetch(imageUrl, { credentials: 'same-origin' })
  if (!response.ok) throw new Error('图片下载失败')
  const blob = await response.blob()
  if (!blob.type.startsWith('image/')) throw new Error('图片格式无效')
  const db = await openDatabase()
  try {
    await new Promise<void>((resolve, reject) => {
      const transaction = db.transaction('images', 'readwrite')
      const store = transaction.objectStore('images')
      store.put({ id: job.id, userId, model: job.model, prompt: job.prompt, createdAt: job.created_at, blob })
      for (const old of [...existing, { id: job.id, createdAt: job.created_at }]
        .sort((a, b) => b.createdAt.localeCompare(a.createdAt)).slice(5)) store.delete(old.id)
      transaction.oncomplete = () => resolve()
      transaction.onerror = () => reject(transaction.error)
    })
  } finally { db.close() }
}
