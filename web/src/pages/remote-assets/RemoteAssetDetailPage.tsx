import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Pencil, Trash2, Plus, Image, Video, FileQuestion, AlertTriangle, CheckCircle, ArrowLeft, Images, List, LayoutGrid } from 'lucide-react'
import Layout from '../../components/Layout'
import ConfirmModal from '../../components/ui/ConfirmModal'
import MediaPreviewModal, { MediaThumb } from '../../components/ui/MediaPreviewModal'
import CopyButton, { googleImagesUrl } from '../../components/ui/CopyButton'
import { normalizeUrls } from '../../components/ui/AddMidiaModal'
import { api } from '../../services/api'
import { useToast } from '../../contexts/ToastContext'

interface Midia {
  id: number
  url: string
  type: string
  extension: string | null
  is_invalid: boolean
  last_used: string | null
}

interface Asset {
  id: number
  name: string
  slug: string
  description: string | null
  midia: Midia[]
}

function TypeIcon({ type }: { type: string }) {
  if (type === 'image') return <Image size={14} className="text-blue-400" />
  if (type === 'video') return <Video size={14} className="text-purple-400" />
  return <FileQuestion size={14} className="text-navy-500" />
}

export default function RemoteAssetDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const toast = useToast()

  const [asset, setAsset] = useState<Asset | null>(null)
  const [bulkUrls, setBulkUrls] = useState('')
  const [addingBulk, setAddingBulk] = useState(false)
  const [showBulk, setShowBulk] = useState(false)
  const [deleteId, setDeleteId] = useState<number | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [filterInvalid, setFilterInvalid] = useState<'all' | 'valid' | 'invalid'>('all')
  const [viewMode, setViewMode] = useState<'table' | 'grid'>('table')
  const [previewMidia, setPreviewMidia] = useState<Midia | null>(null)

  useEffect(() => {
    load()
  }, [id])

  async function load() {
    try {
      const r = await api.get(`/remote-assets/${id}`)
      setAsset({ ...r.data, midia: r.data.midias ?? r.data.midia ?? [] })
    } catch {
      navigate('/remote-assets/assets')
    }
  }

  // Reorganiza o conteúdo colado/digitado para uma URL por linha.
  function handleBulkChange(text: string) {
    const urls = normalizeUrls(text)
    // Se há URLs reconhecíveis, normaliza para uma por linha; senão preserva o texto cru (digitação em andamento).
    setBulkUrls(urls.length ? urls.join('\n') : text)
  }

  function handleBulkPaste(e: React.ClipboardEvent<HTMLTextAreaElement>) {
    const pasted = e.clipboardData.getData('text')
    const urls = normalizeUrls(pasted)
    if (!urls.length) return // deixa o paste padrão acontecer
    e.preventDefault()
    setBulkUrls(prev => {
      const existing = normalizeUrls(prev)
      return Array.from(new Set([...existing, ...urls])).join('\n')
    })
  }

  async function handleBulkAdd() {
    const urls = normalizeUrls(bulkUrls)
    if (!urls.length) return
    setAddingBulk(true)
    try {
      const r = await api.post(`/remote-assets/${id}/midia/bulk`, { urls })
      toast.success(`${Array.isArray(r.data) ? r.data.length : r.data.created} mídias adicionadas!`)
      setBulkUrls('')
      setShowBulk(false)
      load()
    } catch {
      toast.error('Erro ao adicionar mídias.')
    } finally {
      setAddingBulk(false)
    }
  }

  async function handleToggleInvalid(midiaId: number) {
    try {
      const r = await api.patch(`/remote-assets/midia/${midiaId}/toggle-invalid`, {})
      setAsset(a => a ? { ...a, midia: a.midia.map(m => m.id === midiaId ? { ...m, is_invalid: r.data.is_invalid } : m) } : a)
      toast.success(r.data.is_invalid ? 'Mídia marcada como inválida.' : 'Mídia marcada como válida.')
    } catch {
      toast.error('Erro ao atualizar mídia.')
    }
  }

  async function handleDelete() {
    if (deleteId === null) return
    setDeleting(true)
    try {
      await api.delete(`/remote-assets/midia/${deleteId}`)
      setAsset(a => a ? { ...a, midia: a.midia.filter(m => m.id !== deleteId) } : a)
      toast.success('Mídia excluída com sucesso!')
      setPreviewMidia(null)
    } catch {
      toast.error('Erro ao excluir mídia.')
    } finally {
      setDeleting(false)
      setDeleteId(null)
    }
  }

  if (!asset) return null

  const filtered = asset.midia.filter(m =>
    filterInvalid === 'all' ? true :
    filterInvalid === 'invalid' ? m.is_invalid :
    !m.is_invalid
  )

  const countValid = asset.midia.filter(m => !m.is_invalid).length
  const countInvalid = asset.midia.filter(m => m.is_invalid).length

  return (
    <Layout title={asset.name} description={`Remote Assets / ${asset.slug}`}>
      <ConfirmModal
        open={deleteId !== null}
        message="A mídia será removida permanentemente."
        onConfirm={handleDelete}
        onCancel={() => setDeleteId(null)}
        loading={deleting}
      />

      <MediaPreviewModal
        open={previewMidia !== null}
        url={previewMidia?.url ?? null}
        type={previewMidia?.type ?? 'image'}
        onClose={() => setPreviewMidia(null)}
        onRemove={previewMidia ? () => setDeleteId(previewMidia.id) : undefined}
        removing={deleting}
      />

      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-6">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate('/remote-assets/assets')} className="p-2 text-navy-400 hover:text-white bg-navy-800 hover:bg-navy-700 rounded-lg transition-colors">
            <ArrowLeft size={16} />
          </button>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-base font-semibold text-white">{asset.name}</h2>
              <span className="text-xs font-mono text-navy-500 bg-navy-800 px-2 py-0.5 rounded">{asset.slug}</span>
              <CopyButton value={asset.slug} title="Copiar slug" size={12} className="!p-1" />
              <a
                href={googleImagesUrl(asset.name || asset.slug)}
                target="_blank"
                rel="noreferrer"
                title="Buscar no Google Imagens"
                aria-label="Buscar no Google Imagens"
                className="p-1 text-navy-400 hover:text-white bg-navy-800 hover:bg-navy-700 rounded-lg transition-colors"
              >
                <Images size={12} />
              </a>
            </div>
            {asset.description && <p className="text-xs text-navy-400 mt-0.5">{asset.description}</p>}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => navigate(`/remote-assets/assets/${id}/edit`)} className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium text-navy-300 hover:text-white bg-navy-800 hover:bg-navy-700 rounded-lg transition-colors">
            <Pencil size={13} /> Editar
          </button>
          <button onClick={() => setShowBulk(v => !v)} className="flex items-center gap-1.5 px-4 py-2 text-xs font-semibold bg-navy-600 hover:bg-navy-500 text-white rounded-lg transition-colors">
            <Plus size={13} /> Adicionar URLs
          </button>
        </div>
      </div>

      {/* Bulk add */}
      {showBulk && (
        <div className="rounded-xl border border-navy-700 p-5 mb-6" style={{ background: '#141920' }}>
          <p className="text-xs font-medium text-navy-300 mb-2">
            Cole as URLs abaixo — elas são separadas automaticamente, uma por linha.
            {(() => { const n = normalizeUrls(bulkUrls).length; return n > 0 ? <span className="text-navy-500"> ({n} {n === 1 ? 'link' : 'links'})</span> : null })()}
          </p>
          <textarea
            value={bulkUrls}
            onChange={e => handleBulkChange(e.target.value)}
            onPaste={handleBulkPaste}
            rows={5}
            placeholder={"https://exemplo.com/video1.mp4\nhttps://exemplo.com/imagem1.jpg"}
            className="w-full border border-navy-700 rounded-lg px-3 py-2 text-sm text-white placeholder-navy-600 focus:outline-none focus:border-navy-500 resize-y font-mono"
            style={{ background: '#0d1117' }}
          />
          <div className="flex justify-end gap-2 mt-3">
            <button onClick={() => setShowBulk(false)} className="px-4 py-2 text-sm text-navy-400 hover:text-white border border-navy-700 rounded-lg transition-colors">
              Cancelar
            </button>
            <button onClick={handleBulkAdd} disabled={addingBulk || !bulkUrls.trim()} className="px-5 py-2 text-sm font-semibold bg-navy-600 hover:bg-navy-500 disabled:opacity-50 text-white rounded-lg transition-colors">
              {addingBulk ? 'Adicionando...' : 'Adicionar'}
            </button>
          </div>
        </div>
      )}

      {/* Stats + filtro */}
      <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
        <div className="flex gap-2">
          {(['all', 'valid', 'invalid'] as const).map(f => (
            <button
              key={f}
              onClick={() => setFilterInvalid(f)}
              className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
                filterInvalid === f ? 'bg-navy-600 text-white' : 'text-navy-400 bg-navy-800 hover:text-white'
              }`}
            >
              {f === 'all' ? `Todas (${asset.midia.length})` : f === 'valid' ? `Válidas (${countValid})` : `Inválidas (${countInvalid})`}
            </button>
          ))}
        </div>
        <div className="flex gap-1 bg-navy-800 rounded-lg p-1">
          <button
            onClick={() => setViewMode('table')}
            className={`p-1.5 rounded-md transition-colors ${viewMode === 'table' ? 'bg-navy-600 text-white' : 'text-navy-400 hover:text-white'}`}
            title="Visualizar em tabela"
          >
            <List size={14} />
          </button>
          <button
            onClick={() => setViewMode('grid')}
            className={`p-1.5 rounded-md transition-colors ${viewMode === 'grid' ? 'bg-navy-600 text-white' : 'text-navy-400 hover:text-white'}`}
            title="Visualizar em grid"
          >
            <LayoutGrid size={14} />
          </button>
        </div>
      </div>

      {/* Lista de mídias */}
      {filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-navy-600">
          <FileQuestion size={40} className="mb-2 opacity-30" />
          <p className="text-sm">Nenhuma mídia encontrada.</p>
        </div>
      ) : viewMode === 'grid' ? (
        <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 gap-3">
          {filtered.map(m => (
            <div
              key={m.id}
              className={`group relative rounded-xl border border-navy-800 overflow-hidden aspect-square bg-navy-900 transition-colors ${m.is_invalid ? 'opacity-50' : ''}`}
            >
              <button onClick={() => setPreviewMidia(m)} className="w-full h-full block">
                {m.type === 'video' ? (
                  <div className="w-full h-full flex items-center justify-center">
                    <Video size={28} className="text-purple-400" />
                  </div>
                ) : (
                  <img src={m.url} alt="" className="w-full h-full object-cover" loading="lazy" />
                )}
              </button>
              <div className="absolute top-1.5 right-1.5">
                {m.is_invalid
                  ? <AlertTriangle size={14} className="text-red-400 drop-shadow" />
                  : null}
              </div>
              <button
                onClick={() => setDeleteId(m.id)}
                className="absolute bottom-1.5 right-1.5 p-1.5 text-red-400 bg-red-950/90 hover:bg-red-800 rounded-lg opacity-0 group-hover:opacity-100 transition-opacity"
                title="Excluir mídia"
              >
                <Trash2 size={12} />
              </button>
            </div>
          ))}
        </div>
      ) : (
        <div className="rounded-xl border border-navy-800 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-navy-800 text-left" style={{ background: '#141920' }}>
                <th className="px-4 py-3 text-xs font-semibold text-navy-400 uppercase tracking-wider w-16">Preview</th>
                <th className="px-4 py-3 text-xs font-semibold text-navy-400 uppercase tracking-wider w-8">Tipo</th>
                <th className="px-4 py-3 text-xs font-semibold text-navy-400 uppercase tracking-wider">URL</th>
                <th className="px-4 py-3 text-xs font-semibold text-navy-400 uppercase tracking-wider w-24 hidden sm:table-cell">Ext.</th>
                <th className="px-4 py-3 text-xs font-semibold text-navy-400 uppercase tracking-wider w-24">Status</th>
                <th className="px-4 py-3 text-xs font-semibold text-navy-400 uppercase tracking-wider w-28">Ações</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(m => (
                <tr key={m.id} className={`border-b border-navy-900 transition-colors ${m.is_invalid ? 'opacity-50' : 'hover:bg-navy-900'}`}>
                  <td className="px-4 py-3">
                    <MediaThumb url={m.url} type={m.type} onClick={() => setPreviewMidia(m)} />
                  </td>
                  <td className="px-4 py-3"><TypeIcon type={m.type} /></td>
                  <td className="px-4 py-3 max-w-0">
                    <a href={m.url} target="_blank" rel="noreferrer" className="text-navy-300 hover:text-white text-xs font-mono truncate block" title={m.url}>
                      {m.url}
                    </a>
                  </td>
                  <td className="px-4 py-3 hidden sm:table-cell">
                    <span className="text-xs text-navy-500 uppercase">{m.extension ?? '—'}</span>
                  </td>
                  <td className="px-4 py-3">
                    {m.is_invalid
                      ? <span className="flex items-center gap-1 text-xs text-red-400"><AlertTriangle size={11} /> Inválida</span>
                      : <span className="flex items-center gap-1 text-xs text-emerald-400"><CheckCircle size={11} /> Válida</span>
                    }
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1.5">
                      <button
                        onClick={() => handleToggleInvalid(m.id)}
                        className={`p-1.5 rounded-lg transition-colors text-xs ${m.is_invalid ? 'text-emerald-400 bg-emerald-950 hover:bg-emerald-900' : 'text-yellow-400 bg-yellow-950 hover:bg-yellow-900'}`}
                        title={m.is_invalid ? 'Marcar como válida' : 'Marcar como inválida'}
                      >
                        {m.is_invalid ? <CheckCircle size={12} /> : <AlertTriangle size={12} />}
                      </button>
                      <button
                        onClick={() => setDeleteId(m.id)}
                        className="p-1.5 text-red-400 bg-red-950 hover:bg-red-800 rounded-lg transition-colors"
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Layout>
  )
}
