import { useEffect, useId, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { materialColor } from '../lib/scene'
import { scene } from '../lib/scene'

export function Micro({ children }: { children: ReactNode }) {
  return <span className="micro">{children}</span>
}

export function Kicker({ children }: { children: ReactNode }) {
  return <p className="kicker">{children}</p>
}

export function Tagline({ children, size = '1.35rem' }: { children: ReactNode; size?: string }) {
  return (
    <p className="tagline" style={{ fontSize: size }}>
      {children}
    </p>
  )
}

export function SectionHeader({ title, sub }: { title: string; sub?: string }) {
  return (
    <header className="section-head">
      <h2>{title}</h2>
      {sub ? <p>{sub}</p> : null}
    </header>
  )
}

export function Swatch({ material, label }: { material: string; label?: boolean }) {
  return (
    <span className="swatch-row">
      <span className="swatch" style={{ background: materialColor(scene, material) }} aria-hidden="true" />
      {label ? <span>{material}</span> : null}
    </span>
  )
}

export function Chip({
  pressed,
  onClick,
  children,
  label,
}: {
  pressed: boolean
  onClick: () => void
  children: ReactNode
  label?: string
}) {
  return (
    <button type="button" className={pressed ? 'chip on' : 'chip'} aria-pressed={pressed} aria-label={label} onClick={onClick}>
      {children}
    </button>
  )
}

export function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
  name,
}: {
  label: string
  value: T
  options: readonly (readonly [T, string])[]
  onChange: (id: T) => void
  name?: string
}) {
  return (
    <div className="segmented" role="radiogroup" aria-label={label}>
      {options.map(([id, text]) => (
        <button key={id} type="button" role="radio" name={name} aria-checked={value === id} className={value === id ? 'on' : ''} onClick={() => onChange(id)}>
          {text}
        </button>
      ))}
    </div>
  )
}

export function Slider({
  label,
  value,
  text,
  onChange,
}: {
  label: string
  value: number
  text: string
  onChange: (value: number) => void
}) {
  const id = useId()
  return (
    <div className="slider">
      <div className="slider-top">
        <label htmlFor={id}>{label}</label>
        <span id={`${id}-val`}>{text}</span>
      </div>
      <input
        id={id}
        type="range"
        min={0}
        max={100}
        step={1}
        value={Math.round(value * 100)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(value * 100)}
        aria-valuetext={text}
        aria-describedby={`${id}-val`}
        onChange={(e) => onChange(Number(e.target.value) / 100)}
      />
    </div>
  )
}

export function Toggle({
  label,
  sub,
  on,
  onChange,
}: {
  label: string
  sub?: string
  on: boolean
  onChange: (on: boolean) => void
}) {
  return (
    <button type="button" className="toggle" role="switch" aria-checked={on} onClick={() => onChange(!on)}>
      <span>
        <strong>{label}</strong>
        {sub ? <small>{sub}</small> : null}
      </span>
      <span className={on ? 'knob on' : 'knob'} aria-hidden="true" />
    </button>
  )
}

export function BackLink({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link className="back" to={to}>
      <span aria-hidden="true">←</span> {children}
    </Link>
  )
}

export function Still({ names, alt, className = '' }: { names: string[]; alt: string; className?: string }) {
  const key = names.join('|')
  const [index, setIndex] = useState(0)
  useEffect(() => setIndex(0), [key])
  const name = names[index]
  if (!name) return <div className={`still missing ${className}`}>Still render unavailable</div>
  const src = name.includes('/') ? `/${name.replace(/^\/+/, '')}` : `/renders/${name}`
  return <img className={`still ${className}`} src={src} alt={alt} onError={() => setIndex((i) => i + 1)} />
}

export function useMedia(query: string) {
  const [matches, setMatches] = useState(() => (typeof window !== 'undefined' ? window.matchMedia(query).matches : false))
  useEffect(() => {
    const mq = window.matchMedia(query)
    const onChange = () => setMatches(mq.matches)
    onChange()
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [query])
  return matches
}
