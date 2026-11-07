import { useEffect, useRef } from 'react'

function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  const radius = Math.max(0, Math.min(r, w / 2, h / 2))
  ctx.beginPath()
  ctx.roundRect(x, y, w, h, radius)
}

/** Animated chain. The first `lit` links glow, matching the Android hero. */
export function ChainHero({ lit, total = 12 }: { lit: number; total?: number }) {
  const ref = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = ref.current
    if (!canvas) return
    let ctx: CanvasRenderingContext2D | null = null
    try {
      ctx = canvas.getContext('2d')
    } catch {
      ctx = null
    }
    if (!ctx) return
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    let raf = 0
    let lastWidth = 0
    let lastHeight = 0

    const draw = (time: number) => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      const width = canvas.clientWidth || 320
      const height = canvas.clientHeight || 86
      if (width !== lastWidth || height !== lastHeight) {
        lastWidth = width
        lastHeight = height
        canvas.width = Math.max(1, Math.floor(width * dpr))
        canvas.height = Math.max(1, Math.floor(height * dpr))
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.clearRect(0, 0, width, height)
      const t = reduce ? 0 : (time / 5200) * Math.PI * 2
      const glow = reduce ? 0.75 : 0.35 + ((Math.sin((time / 1400) * Math.PI) + 1) / 2) * 0.65
      const linkW = width / (total * 0.62 + 0.6)
      const linkH = linkW * 0.58
      const stroke = Math.max(1.5, linkW * 0.13)
      for (let i = 0; i < total; i++) {
        const cx = linkW * 0.55 + i * linkW * 0.62
        const cy = height / 2 + Math.sin(t + i * 0.55) * height * 0.16
        const on = i < lit
        const angle = Math.cos(t + i * 0.55) * (Math.PI / 180) * 10
        const horizontal = i % 2 === 0
        const w = horizontal ? linkW : linkW * 0.82
        const h = horizontal ? linkH : linkH * 0.62
        ctx.save()
        ctx.translate(cx, cy)
        ctx.rotate(angle)
        if (on) {
          ctx.strokeStyle = `rgba(227, 154, 95, ${0.18 * glow})`
          ctx.lineWidth = stroke * 2.2
          roundRect(ctx, -w / 2 - stroke, -h / 2 - stroke, w + 2 * stroke, h + 2 * stroke, h)
          ctx.stroke()
        }
        ctx.strokeStyle = on ? '#E39A5F' : '#6d5e4e'
        ctx.lineWidth = stroke
        roundRect(ctx, -w / 2, -h / 2, w, h, h / 2)
        ctx.stroke()
        ctx.restore()
      }
      if (!reduce) raf = requestAnimationFrame(draw)
    }

    raf = requestAnimationFrame(draw)
    return () => cancelAnimationFrame(raf)
  }, [lit, total])

  return <canvas ref={ref} className="chain-hero" aria-hidden="true" />
}
