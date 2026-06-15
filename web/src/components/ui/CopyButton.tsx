import { useState } from 'react'
import { Copy, Check } from 'lucide-react'
import { useToast } from '../../contexts/ToastContext'

interface Props {
  value: string
  title?: string
  className?: string
  size?: number
}

/** Botão de copiar com feedback visual (check por 1.5s) + toast. */
export default function CopyButton({ value, title = 'Copiar', className = '', size = 14 }: Props) {
  const toast = useToast()
  const [copied, setCopied] = useState(false)

  async function copy(e: React.MouseEvent) {
    e.preventDefault()
    e.stopPropagation()
    if (!value) return
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
      toast.success('Copiado!')
      setTimeout(() => setCopied(false), 1500)
    } catch {
      toast.error('Não foi possível copiar.')
    }
  }

  return (
    <button
      type="button"
      onClick={copy}
      title={title}
      aria-label={title}
      className={`p-2 rounded-lg transition-colors ${
        copied ? 'text-emerald-400 bg-emerald-950' : 'text-navy-400 hover:text-white bg-navy-800 hover:bg-navy-700'
      } ${className}`}
    >
      {copied ? <Check size={size} /> : <Copy size={size} />}
    </button>
  )
}

/** Monta a URL de busca de imagens grandes no Google. */
export function googleImagesUrl(term: string) {
  return `https://www.google.com/search?q=${encodeURIComponent(term)}&tbm=isch&tbs=il:cl,isz:l`
}
