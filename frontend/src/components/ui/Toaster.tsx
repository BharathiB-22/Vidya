import { createPortal } from 'react-dom'
import { CheckCircle2, AlertCircle, Info } from 'lucide-react'
import { useToast, type Toast } from '@/hooks/useToast'

const ICONS = {
  success: CheckCircle2,
  error:   AlertCircle,
  info:    Info,
}

const STYLES = {
  success: 'bg-green-50 border-green-200 text-green-800',
  error:   'bg-red-50   border-red-200   text-red-800',
  info:    'bg-blue-50  border-blue-200  text-blue-800',
}

const ICON_STYLES = {
  success: 'text-green-600',
  error:   'text-red-500',
  info:    'text-blue-500',
}

function ToastItem({ toast }: { toast: Toast }) {
  const Icon = ICONS[toast.type]
  return (
    <div
      className={`flex items-start gap-3 px-4 py-3 rounded-xl border shadow-lg text-sm
        ${STYLES[toast.type]}`}
    >
      <Icon className={`w-4 h-4 flex-shrink-0 mt-0.5 ${ICON_STYLES[toast.type]}`} />
      <span className="flex-1 leading-snug">{toast.message}</span>
    </div>
  )
}

export function Toaster() {
  const { toasts } = useToast()

  if (toasts.length === 0) return null

  return createPortal(
    <div className="fixed bottom-4 right-4 z-[9999] flex flex-col gap-2 w-80 pointer-events-none">
      {toasts.map((t) => (
        <ToastItem key={t.id} toast={t} />
      ))}
    </div>,
    document.body,
  )
}
