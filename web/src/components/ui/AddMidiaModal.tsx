import { useState } from 'react'
import { X, Images } from 'lucide-react'
import { api } from '../../services/api'
import { useToast } from '../../contexts/ToastContext'
import CopyButton, { googleImagesUrl } from './CopyButton'

/** Extrai URLs de um texto bagunçado (várias por linha, separadas por espaço/vírgula) → uma por linha, sem duplicar. */
export function normalizeUrls(raw: string): string[] {
  const matches = raw.match(/https?:\/\/[^\s,'"<>]+/gi) ?? []
  return Array.from(new Set(matches.map(u => u.replace(/[.,;]+$/, ''))))
}

interface Props {
  open: boolean
  assetId: number
  assetName: string
  assetSlug: string
  onClose: () => void
  /** Chamado após adicionar com sucesso (qtd adicionada). */
  onAdded?: (count: number) => void
}

export default function AddMidiaModal({ open, assetId, assetName, assetSlug, onClose, onAdded }: Props) {
  const toast = useToast()
  const [bulkUrls, setBulkUrls] = useState('')
  const [saving, setSaving] = useState(false)

  if (!open) return null

  function handleChange(text: string) {
    const urls = normalizeUrls(text)
    setBulkUrls(urls.length ? urls.join('\n') : text)
  }

  function handlePaste(e: React.ClipboardEvent<HTMLTextAreaElement>) {
    const urls = normalizeUrls(e.clipboardData.getData('text'))
    if (!urls.length) return
    e.preventDefault()
    setBulkUrls(prev => Array.from(new Set([...normalizeUrls(prev), ...urls])).join('\n'))
  }

  async function handleSubmit() {
    const urls = normalizeUrls(bulkUrls)
    if (!urls.length) return
    setSaving(true)
    try {
      const r = await api.post(`/remote-assets/${assetId}/midia/bulk`, { urls })
      const count = Array.isArray(r.data) ? r.data.length : (r.data.created ?? urls.length)
      toast.success(`${count} ${count === 1 ? 'mídia adicionada' : 'mídias adicionadas'}!`)
      setBulkUrls('')
      onAdded?.(count)
      onClose()
    } catch {
      toast.error('Erro ao adicionar mídias.')
    } finally {
      setSaving(false)
    }
  }

  function close() {
    if (saving) return
    setBulkUrls('')
    onClose()
  }

  const count = normalizeUrls(bulkUrls).length

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/70" onClick={close} />
      <div className="relative w-full max-w-lg rounded-xl border border-navy-700 p-6 shadow-2xl" style={{ background: '#141920' }}>
        <div className="flex items-start justify-between gap-3 mb-4">
          <div className="min-w-0">
            <h3 className="text-base font-semibold text-white truncate">Adicionar mídias</h3>
            <div className="flex items-center gap-1.5 mt-0.5">
              <span className="text-xs font-mono text-navy-500 bg-navy-800 px-2 py-0.5 rounded truncate">{assetSlug}</span>
              <CopyButton value={assetSlug} title="Copiar slug" size={12} className="!p-1" />
              <a
                href={googleImagesUrl(assetName || assetSlug)}
                target="_blank"
                rel="noreferrer"
                title="Buscar no Google Imagens"
                aria-label="Buscar no Google Imagens"
                className="p-1 text-navy-400 hover:text-white bg-navy-800 hover:bg-navy-700 rounded-lg transition-colors"
              >
                <Images size={12} />
              </a>
            </div>
          </div>
          <button onClick={close} className="shrink-0 p-1.5 text-navy-400 hover:text-white bg-navy-800 hover:bg-navy-700 rounded-lg transition-colors" aria-label="Fechar">
            <X size={16} />
          </button>
        </div>

        <p className="text-xs font-medium text-navy-300 mb-2">
          Cole as URLs — elas são separadas automaticamente, uma por linha.
          {count > 0 && <span className="text-navy-500"> ({count} {count === 1 ? 'link' : 'links'})</span>}
        </p>
        <textarea
          autoFocus
          value={bulkUrls}
          onChange={e => handleChange(e.target.value)}
          onPaste={handlePaste}
          rows={6}
          placeholder={'https://exemplo.com/imagem1.jpg\nhttps://exemplo.com/video1.mp4'}
          className="w-full border border-navy-700 rounded-lg px-3 py-2 text-sm text-white placeholder-navy-600 focus:outline-none focus:border-navy-500 resize-y font-mono"
          style={{ background: '#0d1117' }}
        />

        <div className="flex flex-col-reverse sm:flex-row justify-end gap-2 mt-4">
          <button onClick={close} disabled={saving} className="px-4 py-2.5 text-sm font-medium text-navy-300 hover:text-white border border-navy-700 hover:border-navy-500 rounded-lg transition-colors">
            Cancelar
          </button>
          <button onClick={handleSubmit} disabled={saving || count === 0} className="px-5 py-2.5 text-sm font-semibold bg-navy-600 hover:bg-navy-500 disabled:opacity-50 text-white rounded-lg transition-colors">
            {saving ? 'Adicionando...' : `Adicionar${count ? ` ${count}` : ''}`}
          </button>
        </div>
      </div>
    </div>
  )
}
