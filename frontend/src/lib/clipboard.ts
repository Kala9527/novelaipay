export async function copyText(value: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(value)
      return
    } catch {
      // Some browsers expose the API but deny it for the current page.
    }
  }

  const field = document.createElement('textarea')
  const focused = document.activeElement instanceof HTMLElement ? document.activeElement : null
  field.value = value
  field.readOnly = true
  field.style.position = 'fixed'
  field.style.left = '-9999px'
  document.body.append(field)
  try {
    field.focus()
    field.select()
    if (!document.execCommand('copy')) throw new Error('Clipboard copy is unavailable')
  } finally {
    field.remove()
    focused?.focus({ preventScroll: true })
  }
}
