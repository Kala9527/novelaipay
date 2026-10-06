import { useEffect, useRef } from 'react'

type Point = [number, number]
type Constellation = { name: string; stars: Point[]; links: Point[] }
type Speck = { x: number; y: number; vx: number; vy: number; size: number }

const constellations: Constellation[] = [
  { name: 'ARIES', stars: [[8, 72], [31, 44], [58, 28], [82, 35]], links: [[0, 1], [1, 2], [2, 3]] },
  { name: 'TAURUS', stars: [[10, 18], [31, 30], [51, 52], [69, 34], [89, 18], [64, 67], [75, 85]], links: [[0, 1], [1, 2], [2, 3], [3, 4], [2, 5], [5, 6]] },
  { name: 'GEMINI', stars: [[19, 12], [67, 10], [28, 37], [65, 38], [23, 69], [70, 72], [7, 89], [82, 92]], links: [[0, 1], [0, 2], [1, 3], [2, 3], [2, 4], [3, 5], [4, 6], [5, 7]] },
  { name: 'CANCER', stars: [[10, 13], [40, 39], [73, 28], [56, 67], [88, 89]], links: [[0, 1], [1, 2], [1, 3], [3, 4]] },
  { name: 'LEO', stars: [[12, 67], [35, 45], [27, 18], [52, 13], [69, 36], [57, 61], [88, 72], [76, 90]], links: [[0, 1], [1, 2], [2, 3], [3, 4], [4, 5], [5, 1], [5, 6], [6, 7]] },
  { name: 'VIRGO', stars: [[8, 28], [31, 15], [48, 35], [75, 23], [59, 58], [83, 77], [37, 78], [18, 91]], links: [[0, 1], [1, 2], [2, 3], [2, 4], [4, 5], [4, 6], [6, 7]] },
  { name: 'LIBRA', stars: [[14, 25], [76, 18], [35, 55], [68, 60], [18, 86], [86, 88]], links: [[0, 1], [0, 2], [1, 3], [2, 3], [2, 4], [3, 5]] },
  { name: 'SCORPIO', stars: [[8, 13], [27, 24], [43, 39], [52, 58], [68, 68], [84, 60], [87, 79], [70, 91]], links: [[0, 1], [1, 2], [2, 3], [3, 4], [4, 5], [5, 6], [6, 7]] },
  { name: 'SAGITTARIUS', stars: [[12, 18], [40, 30], [71, 12], [58, 49], [88, 60], [48, 80], [20, 76], [77, 91]], links: [[0, 1], [1, 2], [1, 3], [2, 3], [3, 4], [3, 5], [5, 6], [5, 7]] },
  { name: 'CAPRICORN', stars: [[8, 24], [35, 36], [68, 12], [90, 30], [74, 76], [44, 89], [20, 72]], links: [[0, 1], [1, 2], [2, 3], [3, 4], [4, 5], [5, 6], [6, 0], [1, 5]] },
  { name: 'AQUARIUS', stars: [[12, 34], [30, 14], [46, 37], [69, 20], [89, 38], [57, 60], [76, 83], [30, 78]], links: [[0, 1], [1, 2], [2, 3], [3, 4], [2, 5], [5, 6], [5, 7]] },
  { name: 'PISCES', stars: [[15, 22], [32, 10], [45, 29], [32, 46], [52, 60], [72, 44], [87, 59], [79, 82], [61, 88]], links: [[0, 1], [1, 2], [2, 3], [3, 0], [3, 4], [4, 5], [5, 6], [6, 7], [7, 8], [8, 5]] },
]

export function WelcomeAtmosphere() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    const context = canvas?.getContext('2d')
    const shell = canvas?.parentElement
    if (!canvas || !context || !shell) return

    const motion = window.matchMedia('(prefers-reduced-motion: reduce)')
    const offset = { x: 0, y: 0 }
    let drag: Point | null = null
    let width = 0
    let height = 0
    let frame = 0
    let lastFrame = 0
    let specks: Speck[] = []

    const draw = (time: number, advance: boolean) => {
      context.clearRect(0, 0, width, height)
      const dark = document.documentElement.dataset.theme === 'dark'
      const line = dark ? '125, 218, 229' : '33, 91, 172'
      const star = dark ? '178, 239, 244' : '29, 74, 141'
      const accent = dark ? '255, 190, 115' : '181, 88, 52'
      const columns = width < 680 ? 2 : width < 1100 ? 3 : 4
      const rows = Math.ceil(constellations.length / columns)
      const cellWidth = width / columns
      const cellHeight = height / rows
      const scale = Math.min(cellWidth * .65, cellHeight * .62, width < 680 ? 104 : 148) / 100

      constellations.forEach((shape, index) => {
        const column = index % columns
        const row = Math.floor(index / columns)
        const drift = motion.matches ? 0 : time * .00016
        const centerX = cellWidth * (column + .5) + offset.x + Math.sin(drift + index * 1.7) * 11
        const centerY = cellHeight * (row + .5) + offset.y + Math.cos(drift + index * 1.3) * 9
        const points = shape.stars.map(([x, y]) => [centerX + (x - 50) * scale, centerY + (y - 50) * scale] as Point)

        context.lineWidth = dark ? 1.5 : 1.65
        context.strokeStyle = `rgba(${line}, ${dark ? .66 : .62})`
        context.beginPath()
        shape.links.forEach(([start, end]) => {
          context.moveTo(...points[start])
          context.lineTo(...points[end])
        })
        context.stroke()

        points.forEach(([x, y], starIndex) => {
          const prominent = starIndex === 0 || starIndex === Math.floor(points.length / 2)
          context.fillStyle = `rgba(${prominent ? accent : star}, ${dark ? .17 : .15})`
          context.beginPath()
          context.arc(x, y, prominent ? 11 : 8, 0, Math.PI * 2)
          context.fill()
          context.fillStyle = `rgba(${prominent ? accent : star}, .95)`
          context.beginPath()
          context.arc(x, y, prominent ? 3.1 : 2.3, 0, Math.PI * 2)
          context.fill()
        })

        context.fillStyle = `rgba(${star}, ${dark ? .68 : .62})`
        context.font = '600 10px ui-monospace, SFMono-Regular, Consolas, monospace'
        context.textAlign = 'center'
        context.fillText(shape.name, centerX, centerY + scale * 65)
      })

      specks.forEach((speck, index) => {
        if (advance) {
          speck.x = (speck.x + speck.vx + width) % width
          speck.y = (speck.y + speck.vy + height) % height
        }
        for (let next = index + 1; next < specks.length; next++) {
          const other = specks[next]
          const distance = Math.hypot(speck.x - other.x, speck.y - other.y)
          if (distance > 95) continue
          context.strokeStyle = `rgba(${line}, ${(1 - distance / 95) * (dark ? .35 : .3)})`
          context.lineWidth = .8
          context.beginPath()
          context.moveTo(speck.x, speck.y)
          context.lineTo(other.x, other.y)
          context.stroke()
        }
        context.fillStyle = `rgba(${star}, ${dark ? .55 : .48})`
        context.beginPath()
        context.arc(speck.x, speck.y, speck.size, 0, Math.PI * 2)
        context.fill()
      })
    }

    const resize = () => {
      const bounds = canvas.getBoundingClientRect()
      const ratio = Math.min(window.devicePixelRatio || 1, 2)
      width = bounds.width
      height = bounds.height
      canvas.width = Math.round(width * ratio)
      canvas.height = Math.round(height * ratio)
      context.setTransform(ratio, 0, 0, ratio, 0, 0)
      specks = Array.from({ length: Math.min(46, Math.max(22, Math.round(width * height / 28000))) }, (_, index) => ({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - .5) * .3,
        vy: (Math.random() - .5) * .3,
        size: index % 5 === 0 ? 1.8 : 1.1,
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
    const moveDrag = (event: PointerEvent) => {
      if (!drag) return
      offset.x = Math.max(-140, Math.min(140, offset.x + event.clientX - drag[0]))
      offset.y = Math.max(-140, Math.min(140, offset.y + event.clientY - drag[1]))
      drag = [event.clientX, event.clientY]
      draw(performance.now(), false)
    }
    const stopDrag = () => { drag = null }
    const observer = new ResizeObserver(resize)
    const themeObserver = new MutationObserver(() => draw(performance.now(), false))
    observer.observe(canvas)
    themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    motion.addEventListener('change', syncMotion)
    document.addEventListener('visibilitychange', syncMotion)
    shell.addEventListener('pointerdown', startDrag)
    window.addEventListener('pointermove', moveDrag, { passive: true })
    window.addEventListener('pointerup', stopDrag)
    window.addEventListener('pointercancel', stopDrag)
    resize()
    syncMotion()
    return () => {
      window.cancelAnimationFrame(frame)
      observer.disconnect()
      themeObserver.disconnect()
      motion.removeEventListener('change', syncMotion)
      document.removeEventListener('visibilitychange', syncMotion)
      shell.removeEventListener('pointerdown', startDrag)
      window.removeEventListener('pointermove', moveDrag)
      window.removeEventListener('pointerup', stopDrag)
      window.removeEventListener('pointercancel', stopDrag)
    }
  }, [])

  return <canvas ref={canvasRef} className="welcome-atmosphere" aria-hidden="true" />
}
