import { useEffect, useRef, useState } from 'react'

/** True when the user prefers reduced motion. gated on use and cleaned up. */
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState<boolean>(() =>
    typeof window !== 'undefined'
      ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
      : false,
  )
  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    const onChange = (e: MediaQueryListEvent) => setReduced(e.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])
  return reduced
}

/** Observe an element entering the viewport (IntersectionObserver). */
export function useInView<T extends HTMLElement = HTMLDivElement>(options?: {
  once?: boolean
  margin?: string
}) {
  const ref = useRef<T | null>(null)
  const [inView, setInView] = useState(false)
  const once = options?.once !== false

  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (typeof IntersectionObserver === 'undefined') {
      setInView(true)
      return
    }
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setInView(true)
          if (once) io.disconnect()
        } else if (!once) {
          setInView(false)
        }
      },
      { rootMargin: options?.margin ?? '0px 0px -10% 0px', threshold: 0.1 },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [options?.margin, once])

  return { ref, inView } as const
}

/** Ease-out count-up; jumps to the target instantly when disabled. */
export function useCountUp(target: number, options?: { duration?: number; start?: number; decimals?: number; enabled?: boolean }) {
  const { duration = 1400, start = 0, decimals = 0, enabled = true } = options ?? {}
  const [value, setValue] = useState(start)

  useEffect(() => {
    if (!enabled) {
      setValue(target)
      return
    }
    let raf = 0
    const t0 = performance.now()
    const tick = (t: number) => {
      const p = Math.min(1, (t - t0) / duration)
      const eased = 1 - Math.pow(1 - p, 3)
      setValue(start + (target - start) * eased)
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target, duration, start, enabled])

  return { value, formatted: value.toFixed(decimals) }
}