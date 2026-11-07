type Fn = (message: string) => void
const fns = new Set<Fn>()

export function toast(message: string) {
  for (const fn of fns) fn(message)
}

export function subscribeToast(fn: Fn) {
  fns.add(fn)
  return () => {
    fns.delete(fn)
  }
}
