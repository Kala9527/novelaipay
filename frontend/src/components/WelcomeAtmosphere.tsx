import { useEffect, useRef } from 'react'

type Point = [number, number]
type Flow = { points: [Point, Point, Point, Point]; tone: number; speed: number }
type Dust = { x: number; y: number; vx: number; vy: number; size: number; tone: number }

const flows: Flow[] = [
  { points: [[-.08, .16], [.27, .02], [.64, .41], [1.08, .27]], tone: 0, speed: .000035 },
  { points: [[-.08, .43], [.3, .61], [.69, .09], [1.08, .18]], tone: 1, speed: .000028 },
  { points: [[-.08, .72], [.3, .53], [.66, .91], [1.08, .7]], tone: 0, speed: .000032 },
  { points: [[-.08, .92], [.3, 1.02], [.73, .47], [1.08, .53]], tone: 2, speed: .000025 },
  { points: [[.76, -.08], [.52, .3], [.83, .74], [.43, 1.08]], tone: 1, speed: .000022 },
]

function curvePoint([start, controlA, controlB, end]: Flow['points'], t: number): Point {
  const inverse = 1 - t
  return [0, 1].map(axis => inverse ** 3 * start[axis] + 3 * inverse ** 2 * t * controlA[axis] + 3 * inverse * t ** 2 * controlB[axis] + t ** 3 * end[axis]) as Point
}

export function WelcomeAtmosphere() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    const context = canvas?.getContext('2d')
    const shell = canvas?.parentElement
    if (!canvas || !context || !shell) return

    const motion = window.matchMedia('(prefers-reduced-motion: reduce)')
    const pointer = { x: -1000, y: -1000 }
    const offset = { x: 0, y: 0 }
    let drag: Point | null = null
    let width = 0
    let height = 0
    let frame = 0
    let lastFrame = 0
    let dust: Dust[] = []

    const draw = (time: number, advance: boolean) => {
      context.clearRect(0, 0, width, height)
      const dark = document.documentElement.dataset.theme === 'dark'
      const colors = dark ? ['133, 185, 245', '104, 220, 199', '255, 183, 129'] : ['39, 91, 181', '18, 137, 129', '183, 91, 62']
      const parallaxX = motion.matches ? 0 : (pointer.x - width / 2) / Math.max(width, 1) * 10
      const parallaxY = motion.matches ? 0 : (pointer.y - height / 2) / Math.max(height, 1) * 10
      const shiftX = offset.x + (pointer.x < 0 ? 0 : parallaxX)
      const shiftY = offset.y + (pointer.y < 0 ? 0 : parallaxY)
      const compact = width < 620

      // Long curves carry the motion so the small particles never read as a star chart.
      flows.forEach((flow, index) => {
        if (compact && index === 4) return
        const points = flow.points.map(([x, y]) => [x * width + shiftX, y * height + shiftY] as Point)
        context.beginPath()
        context.moveTo(...points[0])
        context.bezierCurveTo(...points[1], ...points[2], ...points[3])
        context.lineWidth = index < 4 ? 1.05 : .8
        context.strokeStyle = `rgba(${colors[flow.tone]}, ${compact ? dark ? .18 : .14 : dark ? .21 : .18})`
        context.stroke()

        for (let particle = 0; particle < 4; particle++) {
          const position = motion.matches ? (particle + 1) / 5 : (time * flow.speed + particle / 4 + index * .13) % 1
          const [x, y] = curvePoint(points as Flow['points'], position)
          const [trailX, trailY] = curvePoint(points as Flow['points'], Math.max(0, position - .028))
          context.beginPath()
          context.moveTo(trailX, trailY)
          context.lineTo(x, y)
          context.lineWidth = compact ? 1.8 : 2.3
          context.strokeStyle = `rgba(${colors[flow.tone]}, ${dark ? .34 : .3})`
          context.stroke()
          context.beginPath()
          context.arc(x, y, particle === 0 ? 2.5 : 1.7, 0, Math.PI * 2)
          context.fillStyle = `rgba(${colors[flow.tone]}, ${dark ? .83 : .72})`
          context.fill()
        }
      })

      dust.forEach(particle => {
        if (advance) {
          particle.x = (particle.x + particle.vx + width) % width
          particle.y = (particle.y + particle.vy + height) % height
        }
        context.beginPath()
        context.arc(particle.x, particle.y, particle.size, 0, Math.PI * 2)
        context.fillStyle = `rgba(${colors[particle.tone]}, ${dark ? .55 : .43})`
        context.fill()
      })

      const corners = (x: number, y: number, size: number, tone: number) => {
        const edge = size * .25
        const h = size * .72
        context.lineWidth = 1.2
        context.strokeStyle = `rgba(${colors[tone]}, ${dark ? .42 : .32})`
        context.beginPath()
        context.moveTo(x, y + edge); context.lineTo(x, y); context.lineTo(x + edge, y)
        context.moveTo(x + size - edge, y); context.lineTo(x + size, y); context.lineTo(x + size, y + edge)
        context.moveTo(x, y + h - edge); context.lineTo(x, y + h); context.lineTo(x + edge, y + h)
        context.moveTo(x + size - edge, y + h); context.lineTo(x + size, y + h); context.lineTo(x + size, y + h - edge)
        context.stroke()
      }
      if (!compact) {
        corners(width * .58 + shiftX, height * .13 + shiftY, 56, 1)
        corners(width * .12 + shiftX, height * .76 + shiftY, 48, 0)
      } else {
        corners(width * .78 + shiftX, height * .25 + shiftY, 27, 1)
      }
    }

    const resize = () => {
      const bounds = canvas.getBoundingClientRect()
      const ratio = Math.min(window.devicePixelRatio || 1, 2)
      width = bounds.width
      height = bounds.height
      canvas.width = Math.round(width * ratio)
      canvas.height = Math.round(height * ratio)
      context.setTransform(ratio, 0, 0, ratio, 0, 0)
      dust = Array.from({ length: Math.min(36, Math.max(20, Math.round(width * height / 32000))) }, (_, index) => ({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - .5) * .36,
        vy: (Math.random() - .5) * .36,
        size: index % 6 === 0 ? 1.8 : 1.1,
        tone: index % 9 === 0 ? 2 : index % 3 === 0 ? 1 : 0,
      }))
      draw(0, false)
    }
    const tick = (time: number) => {
      if (time - lastFrame > 30) {
        draw(time, true)
        lastFrame = time
      }
      frame = window.requestAnimationFrame(tick)
    }
    const syncMotion = () => {
      window.cancelAnimationFrame(frame)
      if (document.visibilityState === 'visible' && !motion.matches) frame = window.requestAnimationFrame(tick)
      else draw(0, false)
    }
    const startDrag = (event: PointerEvent) => {
      if (event.button !== 0 || (event.target as Element).closest('a, button, input, select, textarea, h1, h2, p, .login-kicker, .mirror-carousel, .login-content, .public-header')) return
      drag = [event.clientX, event.clientY]
    }
    const movePointer = (event: PointerEvent) => {
      const bounds = canvas.getBoundingClientRect()
      pointer.x = event.clientX - bounds.left
      pointer.y = event.clientY - bounds.top
      if (drag) {
        offset.x = Math.max(-60, Math.min(60, offset.x + event.clientX - drag[0]))
        offset.y = Math.max(-60, Math.min(60, offset.y + event.clientY - drag[1]))
        drag = [event.clientX, event.clientY]
      }
    }
    const stopDrag = () => { drag = null }
    const clearPointer = () => { pointer.x = -1000; pointer.y = -1000 }
    const observer = new ResizeObserver(resize)
    const themeObserver = new MutationObserver(() => draw(performance.now(), false))
    observer.observe(canvas)
    themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    motion.addEventListener('change', syncMotion)
    document.addEventListener('visibilitychange', syncMotion)
    shell.addEventListener('pointerdown', startDrag)
    window.addEventListener('pointermove', movePointer, { passive: true })
    window.addEventListener('pointerup', stopDrag)
    window.addEventListener('pointercancel', stopDrag)
    window.addEventListener('pointerleave', clearPointer)
    resize()
    syncMotion()
    return () => {
      window.cancelAnimationFrame(frame)
      observer.disconnect()
      themeObserver.disconnect()
      motion.removeEventListener('change', syncMotion)
      document.removeEventListener('visibilitychange', syncMotion)
      shell.removeEventListener('pointerdown', startDrag)
      window.removeEventListener('pointermove', movePointer)
      window.removeEventListener('pointerup', stopDrag)
      window.removeEventListener('pointercancel', stopDrag)
      window.removeEventListener('pointerleave', clearPointer)
    }
  }, [])

  return <canvas ref={canvasRef} className="welcome-atmosphere" aria-hidden="true" />
}
