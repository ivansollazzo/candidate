import { useSyncExternalStore } from "react"

export interface Toast {
  id: number
  text: string
  tone: "success" | "error"
  /** Page the toast links to */
  to?: string
}

let toasts: Toast[] = []
let nextId = 1
const listeners = new Set<() => void>()
const emit = () => listeners.forEach((listener) => listener())

/** Short notice in the corner of the screen, gone after a few seconds. */
export function toast(item: Omit<Toast, "id">) {
  const id = nextId++
  toasts = [...toasts, { ...item, id }]
  emit()
  setTimeout(() => dismissToast(id), 8000)
}

export function dismissToast(id: number) {
  toasts = toasts.filter((item) => item.id !== id)
  emit()
}

export function useToasts() {
  return useSyncExternalStore((listener) => {
    listeners.add(listener)
    return () => listeners.delete(listener)
  }, () => toasts)
}
