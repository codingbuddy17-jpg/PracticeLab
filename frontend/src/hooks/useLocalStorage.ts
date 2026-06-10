import { useState } from 'react'

export function useLocalStorage<T>(key: string, initial: T) {
  const [value, setValue] = useState<T>(() => {
    try {
      const item = localStorage.getItem(key)
      return item ? JSON.parse(item) : initial
    } catch {
      return initial
    }
  })

  const set = (v: T) => {
    setValue(v)
    localStorage.setItem(key, JSON.stringify(v))
  }

  return [value, set] as const
}
