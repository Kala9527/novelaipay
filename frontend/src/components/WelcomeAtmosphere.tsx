import { useEffect, useRef } from 'react'

type Particle = { x: number; y: number; vx: number; vy: number; size: number; accent: boolean }

export function WelcomeAtmosphere() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    const context = canvas?.getContext('2d')
    if (!canvas || !context) return

    const motion = window.matchMedia('(prefers-reduced-motion: reduce)')
    const pointer = { x: -1000, y: -1000 }
    let width = 0
    let height = 0
    let frame = 0
    let particles: Particle[] = []
    let lastFrame = 0

    const resize = () => {
      const bounds = canvas.getBoundingClientRect()
      const ratio = Math.min(window.devicePixelRatio || 1, 2)
      width = bounds.width
      height = bounds.height
      canvas.width = Math.round(width * ratio)
      canvas.height = Math.round(height * ratio)
      context.setTransform(ratio, 0, 0, ratio, 0, 0)
      const count = Math.min(64, Math.max(26, Math.round(width * height / 23000)))
      particles = Array.from({ length: count }, (_, index) => ({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - .5) * .26,
        vy: (Math.random() - .5) * .26,
        size: index % 7 === 0 ? 2.4 : 1.3,
        accent: index % 6 === 0,
      }))
      draw(false)
    }

    const draw = (advance: boolean) => {
      context.clearRect(0, 0, width, height)
      const dark = document.documentElement.dataset.theme === 'dark'
      const blue = dark ? '143, 184, 255' : '49, 104, 202'
      const teal = dark ? '100, 219, 202' : '14, 143, 133'
      const range = width < 600 ? 125 : 170

      particles.forEach((particle, index) => {
        if (advance) {
          particle.x += particle.vx
          particle.y += particle.vy
          if (particle.x < -12) particle.x = width + 12
          if (particle.x > width + 12) particle.x = -12
          if (particle.y < -12) particle.y = height + 12
          if (particle.y > height + 12) particle.y = -12
        }
        for (let next = index + 1; next < particles.length; next++) {
          const other = particles[next]
          const distance = Math.hypot(particle.x - other.x, particle.y - other.y)
          if (distance > range) continue
          const nearPointer = Math.hypot((particle.x + other.x) / 2 - pointer.x, (particle.y + other.y) / 2 - pointer.y) < 170
          context.strokeStyle = `rgba(${blue}, ${(1 - distance / range) * (nearPointer ? .31 : .15)})`
          context.lineWidth = nearPointer ? 1 : .7
          context.beginPath()
          context.moveTo(particle.x, particle.y)
          context.lineTo(other.x, other.y)
          context.stroke()
        }
        const glow = Math.hypot(particle.x - pointer.x, particle.y - pointer.y) < 120
        context.fillStyle = `rgba(${particle.accent ? teal : blue}, ${glow ? .8 : .44})`
        context.beginPath()
        context.arc(particle.x, particle.y, particle.size + (glow ? .7 : 0), 0, Math.PI * 2)
        context.fill()
      })
    }

    const tick = (time: number) => {
      if (time - lastFrame > 30) {
        draw(true)
        lastFrame = time
      }
      frame = window.requestAnimationFrame(tick)
    }
    const syncMotion = () => {
      window.cancelAnimationFrame(frame)
      if (document.visibilityState === 'visible' && !motion.matches) frame = window.requestAnimationFrame(tick)
      else draw(false)
    }
    const trackPointer = (event: PointerEvent) => {
      const bounds = canvas.getBoundingClientRect()
      pointer.x = event.clientX - bounds.left
      pointer.y = event.clientY - bounds.top
    }
    const resetPointer = () => { pointer.x = -1000; pointer.y = -1000 }
    const observer = new ResizeObserver(resize)
    const themeObserver = new MutationObserver(() => draw(false))
    observer.observe(canvas)
    themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    motion.addEventListener('change', syncMotion)
    document.addEventListener('visibilitychange', syncMotion)
    window.addEventListener('pointermove', trackPointer, { passive: true })
    window.addEventListener('pointerleave', resetPointer)
    resize()
    syncMotion()
    return () => {
      window.cancelAnimationFrame(frame)
      observer.disconnect()
      themeObserver.disconnect()
      motion.removeEventListener('change', syncMotion)
      document.removeEventListener('visibilitychange', syncMotion)
      window.removeEventListener('pointermove', trackPointer)
      window.removeEventListener('pointerleave', resetPointer)
    }
  }, [])

  return <canvas ref={canvasRef} className="welcome-atmosphere" aria-hidden="true" />
}
