import { useSyncExternalStore } from "react"

export interface Toast {
  id: number
  title: string
  /** Second line, e.g. the application concerned */
  description?: string
  tone: "success" | "error" | "warning"
  /** Page the toast links to */
  to?: string
}

/** How long a toast stays, unless the pointer is on it */
export const TOAST_MS = 8000

let toasts: Toast[] = []
let nextId = 1
const listeners = new Set<() => void>()
const emit = () => listeners.forEach((listener) => listener())

/** Short notice in the corner of the screen; the Toaster removes it when its time is up. */
export function toast(item: Omit<Toast, "id">) {
  toasts = [...toasts, { ...item, id: nextId++ }]
  emit()
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
