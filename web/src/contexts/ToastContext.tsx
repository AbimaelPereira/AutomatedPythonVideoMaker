import { createContext, useCallback, useContext, useState } from 'react'
import { CheckCircle, XCircle, AlertCircle, X } from 'lucide-react'

type ToastType = 'success' | 'error' | 'warning'

interface Toast {
  id: number
  type: ToastType
  message: string
}

interface ToastContextType {
  success: (message: string) => void
  error: (message: string) => void
  warning: (message: string) => void
}

const ToastContext = createContext<ToastContextType>({} as ToastContextType)

let counter = 0

const config: Record<ToastType, { icon: React.ElementType; bg: string; border: string; text: string }> = {
  success: { icon: CheckCircle, bg: '#0d2b1a', border: '#166534', text: '#4ade80' },
  error:   { icon: XCircle,     bg: '#2b0d0d', border: '#991b1b', text: '#f87171' },
  warning: { icon: AlertCircle, bg: '#2b1f0d', border: '#92400e', text: '#fbbf24' },
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const remove = useCallback((id: number) => {
    setToasts(t => t.filter(x => x.id !== id))
  }, [])

  const add = useCallback((type: ToastType, message: string) => {
    const id = ++counter
    setToasts(t => [...t, { id, type, message }])
    setTimeout(() => remove(id), 4000)
  }, [remove])

  const success = useCallback((m: string) => add('success', m), [add])
  const error   = useCallback((m: string) => add('error', m),   [add])
  const warning = useCallback((m: string) => add('warning', m), [add])

  return (
    <ToastContext.Provider value={{ success, error, warning }}>
      {children}
      <div className="fixed bottom-5 right-5 z-50 flex flex-col gap-2 w-80 max-w-[calc(100vw-2.5rem)]">
        {toasts.map(toast => {
          const { icon: Icon, bg, border, text } = config[toast.type]
          return (
            <div
              key={toast.id}
              className="flex items-start gap-3 px-4 py-3 rounded-xl shadow-lg border text-sm animate-slide-in"
              style={{ background: bg, borderColor: border }}
            >
              <Icon size={18} style={{ color: text }} className="shrink-0 mt-0.5" />
              <span className="flex-1 text-white leading-snug">{toast.message}</span>
              <button onClick={() => remove(toast.id)} className="shrink-0 text-gray-500 hover:text-white transition-colors">
                <X size={14} />
              </button>
            </div>
          )
        })}
      </div>
    </ToastContext.Provider>
  )
}

export const useToast = () => useContext(ToastContext)
