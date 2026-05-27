import { useState } from 'react'
import { ChevronDown, ChevronUp, Film, Tv2 } from 'lucide-react'

// ── tipos exportados para reuso futuro ────────────────────────────────────────

export interface SceneNarration {
  text: string
  subtitles?: boolean
}

export interface Scene {
  id: string
  narration: SceneNarration
}

export interface YoutubeData {
  title: string
  description: string
  tags: string[]
  publish_at: string
}

export interface ClipJson {
  slug: string
  channel_name: string
  output_ratio?: string
  scenes: Scene[]
  youtube: YoutubeData
}

interface Props {
  index: number
  clip: ClipJson
  onChange: (updated: ClipJson) => void
}

type Tab = 'cenas' | 'youtube'

const BORDER = '1px solid #1e2229'

export default function ClipJsonEditor({ index, clip, onChange }: Props) {
  const [open, setOpen]       = useState(false)
  const [tab, setTab]         = useState<Tab>('cenas')

  function setScene(i: number, text: string) {
    const scenes = clip.scenes.map((s, si) =>
      si === i ? { ...s, narration: { ...s.narration, text } } : s
    )
    onChange({ ...clip, scenes })
  }

  function setYoutube(field: keyof YoutubeData, value: string | string[]) {
    onChange({ ...clip, youtube: { ...clip.youtube, [field]: value } })
  }

  function setTags(raw: string) {
    setYoutube('tags', raw.split(',').map(t => t.trim()).filter(Boolean))
  }

  const tabBtn = (t: Tab, label: string, Icon: React.ElementType) => (
    <button
      onClick={() => setTab(t)}
      className="flex items-center gap-1.5 px-4 py-2 text-xs font-medium transition-colors rounded-t-lg"
      style={{
        color:       tab === t ? '#e8edf5' : '#4a5568',
        borderBottom: tab === t ? '2px solid #3d5ca8' : '2px solid transparent',
      }}
    >
      <Icon size={12} /> {label}
    </button>
  )

  return (
    <div
      className="rounded-xl overflow-hidden transition-all"
      style={{ background: '#0d1117', border: BORDER }}
    >
      {/* ── Cabeçalho do card ── */}
      <button
        className="w-full flex items-center justify-between px-4 py-3 text-left group"
        onClick={() => setOpen(v => !v)}
      >
        <div className="flex items-center gap-3 min-w-0">
          <span
            className="text-[10px] font-mono px-2 py-0.5 rounded shrink-0"
            style={{ background: '#1a1e25', color: '#4a5568' }}
          >
            {String(index + 1).padStart(2, '0')}
          </span>
          <div className="min-w-0">
            <p className="text-sm font-medium text-white truncate">{clip.youtube.title || clip.slug}</p>
            <p className="text-[11px] truncate" style={{ color: '#374151' }}>
              {clip.slug} · {clip.scenes.length} cenas
            </p>
          </div>
        </div>
        <span className="text-navy-600 group-hover:text-navy-400 transition-colors shrink-0 ml-3">
          {open ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </span>
      </button>

      {/* ── Conteúdo expandido ── */}
      {open && (
        <div style={{ borderTop: BORDER }}>
          {/* Tabs */}
          <div className="flex px-4 gap-1" style={{ borderBottom: BORDER }}>
            {tabBtn('cenas',   'Cenas',   Film)}
            {tabBtn('youtube', 'YouTube', Tv2)}
          </div>

          <div className="p-4">
            {/* ── Tab Cenas ── */}
            {tab === 'cenas' && (
              <div className="space-y-3">
                {clip.scenes.map((scene, i) => (
                  <div key={scene.id} className="flex gap-3">
                    <span
                      className="text-[10px] font-mono pt-2.5 shrink-0 w-8 text-right"
                      style={{ color: '#2a3040' }}
                    >
                      {scene.id}
                    </span>
                    <textarea
                      value={scene.narration.text}
                      onChange={e => setScene(i, e.target.value)}
                      rows={2}
                      className="flex-1 text-sm rounded-lg px-3 py-2 text-white resize-none focus:outline-none rc-scroll transition-colors"
                      style={{
                        background:  '#13161b',
                        border:      '1px solid #1e2229',
                        color:       '#c5d0e6',
                        lineHeight:  '1.5',
                      }}
                      onFocus={e => (e.currentTarget.style.borderColor = '#2f4a8f')}
                      onBlur={e  => (e.currentTarget.style.borderColor = '#1e2229')}
                    />
                  </div>
                ))}
              </div>
            )}

            {/* ── Tab YouTube ── */}
            {tab === 'youtube' && (
              <div className="space-y-4">
                {/* Título */}
                <Field label="Título">
                  <input
                    value={clip.youtube.title}
                    onChange={e => setYoutube('title', e.target.value)}
                    className="w-full text-sm rounded-lg px-3 py-2 text-white focus:outline-none"
                    style={{ background: '#13161b', border: '1px solid #1e2229', color: '#c5d0e6' }}
                    onFocus={e => (e.currentTarget.style.borderColor = '#2f4a8f')}
                    onBlur={e  => (e.currentTarget.style.borderColor = '#1e2229')}
                  />
                </Field>

                {/* Descrição */}
                <Field label="Descrição">
                  <textarea
                    value={clip.youtube.description}
                    onChange={e => setYoutube('description', e.target.value)}
                    rows={4}
                    className="w-full text-sm rounded-lg px-3 py-2 text-white resize-none focus:outline-none rc-scroll"
                    style={{ background: '#13161b', border: '1px solid #1e2229', color: '#c5d0e6' }}
                    onFocus={e => (e.currentTarget.style.borderColor = '#2f4a8f')}
                    onBlur={e  => (e.currentTarget.style.borderColor = '#1e2229')}
                  />
                </Field>

                {/* Tags */}
                <Field label="Tags" hint="separadas por vírgula">
                  <input
                    value={clip.youtube.tags.join(', ')}
                    onChange={e => setTags(e.target.value)}
                    className="w-full text-sm rounded-lg px-3 py-2 text-white focus:outline-none"
                    style={{ background: '#13161b', border: '1px solid #1e2229', color: '#c5d0e6' }}
                    onFocus={e => (e.currentTarget.style.borderColor = '#2f4a8f')}
                    onBlur={e  => (e.currentTarget.style.borderColor = '#1e2229')}
                  />
                  {/* Preview das tags */}
                  {clip.youtube.tags.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 mt-2">
                      {clip.youtube.tags.map((tag, ti) => (
                        <span
                          key={ti}
                          className="text-[10px] px-2 py-0.5 rounded-full"
                          style={{ background: '#1a1e25', color: '#4a5568' }}
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  )}
                </Field>

                {/* Data de publicação */}
                <Field label="Data de publicação">
                  <input
                    type="datetime-local"
                    value={clip.youtube.publish_at
                      ? clip.youtube.publish_at.replace(' ', 'T').substring(0, 16)
                      : ''}
                    onChange={e => setYoutube('publish_at', e.target.value.replace('T', ' ') + ':00')}
                    className="w-full text-sm rounded-lg px-3 py-2 text-white focus:outline-none"
                    style={{ background: '#13161b', border: '1px solid #1e2229', color: '#c5d0e6', colorScheme: 'dark' }}
                    onFocus={e => (e.currentTarget.style.borderColor = '#2f4a8f')}
                    onBlur={e  => (e.currentTarget.style.borderColor = '#1e2229')}
                  />
                </Field>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="flex items-center gap-2 mb-1.5">
        <label className="text-xs font-medium" style={{ color: '#4a5568' }}>{label}</label>
        {hint && <span className="text-[10px]" style={{ color: '#2a3040' }}>{hint}</span>}
      </div>
      {children}
    </div>
  )
}
