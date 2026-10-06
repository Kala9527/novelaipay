import { useEffect, useState } from 'react'
import { ChevronLeft, ChevronRight, Pause, Play } from 'lucide-react'
import { usePreferences } from '../lib/preferences'
import studioArt from '../assets/studio-art.jpg'

const slides = [
  { image: studioArt, position: '24% 43%', number: '01' },
  { image: studioArt, position: '50% 48%', number: '02' },
  { image: studioArt, position: '78% 42%', number: '03' },
]

const labels = {
  zh: { carousel: '镜面作品轮播', previous: '上一张', next: '下一张', pause: '暂停轮播', play: '继续轮播', slide: (number: number) => `查看第 ${number} 张` },
  en: { carousel: 'Mirrored artwork carousel', previous: 'Previous image', next: 'Next image', pause: 'Pause carousel', play: 'Resume carousel', slide: (number: number) => `Show image ${number}` },
  ja: { carousel: 'ミラー作品カルーセル', previous: '前の画像', next: '次の画像', pause: '自動切替を停止', play: '自動切替を再開', slide: (number: number) => `${number} 枚目を表示` },
}

export function WelcomeCarousel() {
  const { locale } = usePreferences()
  const [active, setActive] = useState(0)
  const [paused, setPaused] = useState(false)
  const [hovered, setHovered] = useState(false)
  const [focused, setFocused] = useState(false)
  const [reducedMotion, setReducedMotion] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches)
  const label = labels[locale]

  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)')
    const update = () => setReducedMotion(media.matches)
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [])
  useEffect(() => {
    if (paused || hovered || focused || reducedMotion) return
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') setActive(current => (current + 1) % slides.length)
    }, 5000)
    return () => window.clearInterval(timer)
  }, [paused, hovered, focused, reducedMotion, active])

  function move(offset: number) { setActive(current => (current + offset + slides.length) % slides.length) }

  return <section className={`mirror-carousel ${paused || hovered || focused ? 'is-paused' : ''}`} aria-label={label.carousel}
    onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}
    onFocusCapture={() => setFocused(true)}
    onBlurCapture={event => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setFocused(false) }}>
    <div className="mirror-stage" aria-hidden="true">
      {slides.map((slide, index) => {
        const place = index === active ? 'active' : index === (active + 1) % slides.length ? 'next' : 'previous'
        return <div className={`mirror-slide mirror-slide-${place}`} key={slide.number}>
          <div className="mirror-image"><img src={slide.image} alt="" style={{ objectPosition: slide.position }} /><span className="mirror-index">{slide.number}</span></div>
          <div className="mirror-reflection"><img src={slide.image} alt="" style={{ objectPosition: slide.position }} /></div>
        </div>
      })}
      <span className="mirror-stage-line mirror-stage-line-top" />
      <span className="mirror-stage-line mirror-stage-line-bottom" />
    </div>
    <div className="mirror-controls">
      <div className="mirror-pagination" aria-label={label.carousel}>{slides.map((slide, index) => <button key={slide.number} type="button" className={index === active ? 'active' : ''} aria-label={label.slide(index + 1)} aria-current={index === active ? 'true' : undefined} title={label.slide(index + 1)} onClick={() => setActive(index)}><span>{slide.number}</span></button>)}</div>
      <div className="mirror-actions"><button type="button" className="icon-button" aria-label={label.previous} title={label.previous} onClick={() => move(-1)}><ChevronLeft size={17} /></button><button type="button" className="icon-button" aria-label={paused ? label.play : label.pause} title={paused ? label.play : label.pause} onClick={() => setPaused(value => !value)}>{paused ? <Play size={15} /> : <Pause size={15} />}</button><button type="button" className="icon-button" aria-label={label.next} title={label.next} onClick={() => move(1)}><ChevronRight size={17} /></button></div>
    </div>
  </section>
}
