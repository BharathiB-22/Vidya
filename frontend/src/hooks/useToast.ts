import { useState, useEffect } from 'react'

export type ToastType = 'success' | 'error' | 'info'

export interface Toast {
  id: string
  message: string
  type: ToastType
}

type Listener = (toasts: Toast[]) => void

let _toasts: Toast[] = []
const _listeners = new Set<Listener>()

function notify() {
  const snapshot = [..._toasts]
  _listeners.forEach((l) => l(snapshot))
}

export function addToast(message: string, type: ToastType = 'success', duration = 3500) {
  const id = Math.random().toString(36).slice(2, 9)
  _toasts = [..._toasts, { id, message, type }]
  notify()
  setTimeout(() => {
    _toasts = _toasts.filter((t) => t.id !== id)
    notify()
  }, duration)
}

export function useToast() {
  const [toasts, setToasts] = useState<Toast[]>(_toasts)

  useEffect(() => {
    _listeners.add(setToasts)
    return () => { _listeners.delete(setToasts) }
  }, [])

  return { toasts }
}
