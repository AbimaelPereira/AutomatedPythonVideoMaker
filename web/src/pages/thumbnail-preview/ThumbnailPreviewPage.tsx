import { useEffect, useMemo, useRef, useState } from 'react'
import Layout from '../../components/Layout'
import FormField from '../../components/ui/FormField'
import Select from '../../components/ui/Select'
import Slider from '../../components/ui/Slider'
import Toggle from '../../components/ui/Toggle'
import ColorPicker from '../../components/ui/ColorPicker'
import { api } from '../../services/api'
import { useDebouncedValue } from '../../hooks/useDebouncedValue'
import {
  Copy, Check, Plus, Trash2, ChevronUp, ChevronDown,
  Image as ImageIcon, Type, Blend, Sparkles, RotateCcw, AlertTriangle, Download,
} from 'lucide-react'

interface FontOption { path: string; label: string; family: string }

const DEFAULT_FONT = './assets/fonts/Montserrat/Montserrat-Black.ttf'

// ----------------------------------------------------------------------
// Modelo
// ----------------------------------------------------------------------

type ElementType = 'gradient' | 'text_box' | 'image'
type BackgroundType = 'ai' | 'image' | 'color'

interface Placement {
  anchor_x: string
  anchor_y: string
  /** Largura em % da referência. 0 = não declarar (deixa o motor decidir). */
  width: number
  /** Altura em % da referência. 0 = não declarar. */
  height: number
  /** true = medir contra a tela inteira; false = contra a área segura. */
  full_screen: boolean
}

interface GradientStop { color: string; opacity: number; at: number }

interface BaseElement {
  id: string
  type: ElementType
  placement: Placement
}

interface GradientElement extends BaseElement {
  type: 'gradient'
  direction: 'to_top' | 'to_bottom' | 'to_left' | 'to_right'
  stops: GradientStop[]
}

interface TextElement extends BaseElement {
  type: 'text_box'
  content: string
  font_path: string
  font_size: number
  text_color: string
  align: 'left' | 'center' | 'right'
  line_spacing: number
  stroke_enabled: boolean
  stroke_color: string
  stroke_width: number
  shadow_enabled: boolean
  shadow_color: string
  shadow_opacity: number
  shadow_blur: number
  shadow_offset: [number, number]
}

interface ImageElement extends BaseElement {
  type: 'image'
  source: string
  border_radius: number
  opacity: number
}

type Element = GradientElement | TextElement | ImageElement

interface State {
  width: number
  height: number
  // fundo
  bg_type: BackgroundType
  bg_prompt: string
  bg_model: string
  bg_source: string
  bg_color: string
  bg_fit_mode: string
  bg_focus: string
  // elementos
  elements: Element[]
}

const newId = () => Math.random().toString(36).slice(2, 10)

const fullScreenPlacement = (): Placement => ({
  anchor_x: 'center', anchor_y: 'center', width: 100, height: 100, full_screen: true,
})

const newGradient = (): GradientElement => ({
  id: newId(), type: 'gradient', direction: 'to_top',
  stops: [
    { color: '#000000', opacity: 0.9, at: 0 },
    { color: '#000000', opacity: 0, at: 0.6 },
  ],
  placement: fullScreenPlacement(),
})

const newText = (): TextElement => ({
  id: newId(), type: 'text_box',
  content: 'ELE NUNCA\nTE ABANDONOU',
  font_path: DEFAULT_FONT, font_size: 96, text_color: '#FFE24A',
  align: 'left', line_spacing: 1.05,
  stroke_enabled: true, stroke_color: '#000000', stroke_width: 8,
  shadow_enabled: true, shadow_color: '#000000', shadow_opacity: 0.8,
  shadow_blur: 4, shadow_offset: [6, 6],
  placement: { anchor_x: 'left', anchor_y: 'bottom', width: 62, height: 0, full_screen: false },
})

const newImage = (): ImageElement => ({
  id: newId(), type: 'image', source: '', border_radius: 0, opacity: 1,
  placement: { anchor_x: 'right', anchor_y: 'top', width: 20, height: 0, full_screen: false },
})

const DEFAULT: State = {
  width: 1280, height: 720,
  bg_type: 'ai',
  bg_prompt: 'dark moody cathedral interior, dramatic god rays, cinematic, 4k',
  bg_model: 'flux',
  bg_source: '',
  bg_color: '#101418',
  bg_fit_mode: 'cover',
  bg_focus: 'center',
  elements: [newGradient(), newText()],
}

const SIZE_PRESETS = [
  { value: '1280x720', label: 'YouTube 16:9 — 1280×720' },
  { value: '1920x1080', label: 'Full HD 16:9 — 1920×1080' },
  { value: '1080x1920', label: 'Shorts 9:16 — 1080×1920' },
]

// ----------------------------------------------------------------------
// State → JSON do videomaker
// ----------------------------------------------------------------------

/** Converte um Placement no bloco `placement` do JSON (omitindo o que é vazio). */
function toPlacement(p: Placement) {
  // 0 significa "não declarar": sem `width`, o motor usa o tamanho natural do
  // elemento; sem `height`, mantém a proporção. Só emitimos o que foi definido.
  return {
    anchor: [p.anchor_x, p.anchor_y],
    ...(p.width > 0 && { width: `${p.width}%` }),
    ...(p.height > 0 && { height: `${p.height}%` }),
    ...(p.full_screen && { relative_to: 'screen' }),
  }
}

function toElementJson(el: Element): Record<string, unknown> {
  if (el.type === 'gradient') {
    return {
      type: 'gradient',
      direction: el.direction,
      stops: el.stops.map(s => ({ color: s.color, opacity: s.opacity, at: s.at })),
      placement: toPlacement(el.placement),
    }
  }
  if (el.type === 'text_box') {
    return {
      type: 'text_box',
      content: el.content,
      style: {
        font_path: el.font_path,
        font_size: el.font_size,
        text_color: el.text_color,
        background_color: 'transparent',
        align: el.align,
        line_spacing: el.line_spacing,
        ...(el.stroke_enabled && {
          stroke_color: el.stroke_color, stroke_width: el.stroke_width,
        }),
        ...(el.shadow_enabled && {
          shadow: {
            color: el.shadow_color, opacity: el.shadow_opacity,
            blur: el.shadow_blur, offset: el.shadow_offset,
          },
        }),
      },
      placement: toPlacement(el.placement),
    }
  }
  return {
    type: 'image',
    source: el.source,
    ...(el.border_radius > 0 && { border_radius: el.border_radius }),
    ...(el.opacity < 1 && { opacity: el.opacity }),
    placement: toPlacement(el.placement),
  }
}

/** Bloco `background` do JSON — null quando não há fundo configurado. */
function toBackgroundJson(s: State): Record<string, unknown> | null {
  if (s.bg_type === 'color') {
    return { visual: { type: 'color', source: s.bg_color } }
  }
  if (s.bg_type === 'image') {
    if (!s.bg_source) return null
    return {
      visual: {
        type: 'image', source: s.bg_source,
        fit_mode: s.bg_fit_mode, focus: s.bg_focus,
      },
    }
  }
  if (!s.bg_prompt) return null
  return { visual: { type: 'ai', prompt: s.bg_prompt, model: s.bg_model } }
}

/** Bloco `youtube.thumbnail` completo, pronto para colar no JSON do vídeo. */
function toThumbnailJson(s: State) {
  return {
    type: 'scene',
    width: s.width,
    height: s.height,
    ...(toBackgroundJson(s) && { background: toBackgroundJson(s) }),
    visual_elements: s.elements.map(toElementJson),
  }
}

// ----------------------------------------------------------------------
// Página
// ----------------------------------------------------------------------

export default function ThumbnailPreviewPage() {
  const [s, setS] = useState<State>(DEFAULT)
  const [fonts, setFonts] = useState<FontOption[]>([])
  const [previewUrl, setPreviewUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [warnings, setWarnings] = useState<string[]>([])
  const [copied, setCopied] = useState(false)

  // Fundo de IA gerado e fixado: enquanto existe, o preview o reaproveita em
  // vez de gerar uma imagem nova a cada ajuste de texto.
  const [backgroundId, setBackgroundId] = useState<string | null>(null)
  const [generatingBg, setGeneratingBg] = useState(false)

  // 200ms: o render caiu para ~2s, então esperar mais só atrasa o retorno
  // visual. Arrastar um slider ainda agrupa os passos numa requisição só.
  const debounced = useDebouncedValue(s, 200)
  const reqId = useRef(0)

  const set = <K extends keyof State>(k: K, v: State[K]) => setS(p => ({ ...p, [k]: v }))

  useEffect(() => {
    api.get<FontOption[]>('/thumbnail-preview/fonts')
      .then(r => setFonts(r.data)).catch(() => setFonts([]))
  }, [])

  // O fundo de IA é caro: o preview automático só roda quando já existe um
  // fundo fixado, ou quando o fundo é local (cor/imagem) e portanto barato.
  const bgIsCheap = s.bg_type !== 'ai'
  const canAutoPreview = bgIsCheap || backgroundId !== null

  /** Lê o header de avisos (asset que falhou, fallback silencioso da engine). */
  const readWarnings = (raw: unknown): string[] => {
    if (typeof raw !== 'string') return []
    try { return JSON.parse(raw) } catch { return [] }
  }

  const fetchPreview = (state: State, bgId: string | null) => {
    const id = ++reqId.current
    setLoading(true); setError('')

    const payload = {
      width: state.width,
      height: state.height,
      visual_elements: state.elements.map(toElementJson),
      // Um fundo fixado vence o declarado — é a imagem que o usuário aprovou.
      ...(bgId
        ? { background_id: bgId }
        : { background: toBackgroundJson(state) }),
    }

    api.post('/thumbnail-preview', payload, { responseType: 'arraybuffer' })
      .then(r => {
        // Resposta obsoleta (outra requisição saiu depois): descarta o
        // resultado, mas NÃO mexe em `loading` — quem manda no spinner é a
        // requisição mais recente, que ainda está em voo.
        if (id !== reqId.current) return
        const bytes = new Uint8Array(r.data)
        let bin = ''
        for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i])
        const mime = r.headers['content-type'] ?? 'image/png'
        setPreviewUrl(`data:${mime};base64,${btoa(bin)}`)
        setWarnings(readWarnings(r.headers['x-thumbnail-warnings']))
        setLoading(false)
      })
      .catch(err => {
        if (id !== reqId.current) return
        const status = err?.response?.status
        if (status === 410) {
          // O fundo expirou no servidor: solta a referência para o usuário gerar outro.
          setBackgroundId(null)
          setError('O fundo gerado expirou — gere novamente.')
        } else if (status === 401) {
          setError('Sessão expirada — faça logout e login novamente.')
        } else {
          let msg = 'Falha ao gerar preview'
          try {
            const buf = err?.response?.data
            if (buf) msg = JSON.parse(new TextDecoder().decode(buf))?.detail ?? msg
          } catch { /* mantém a mensagem genérica */ }
          setError(msg)
        }
        setLoading(false)
      })
  }

  useEffect(() => {
    if (!canAutoPreview) return
    fetchPreview(debounced, backgroundId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced, backgroundId, canAutoPreview])

  /** Gera (ou regera) o fundo de IA. Cada geração substitui a anterior. */
  const generateBackground = async () => {
    const background = toBackgroundJson(s)
    if (!background) {
      setError('Descreva o prompt do fundo antes de gerar.')
      return
    }

    setGeneratingBg(true); setError('')
    const previous = backgroundId
    try {
      const { data } = await api.post('/thumbnail-preview/background', {
        background, width: s.width, height: s.height,
      })
      setBackgroundId(data.background_id)
      setWarnings(data.warnings ?? [])
      // O anterior já não é referenciado por ninguém: libera o disco do servidor.
      if (previous) api.delete(`/thumbnail-preview/background/${previous}`).catch(() => {})
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? 'Falha ao gerar o fundo')
    } finally {
      setGeneratingBg(false)
    }
  }

  /** Solta o fundo fixado, sem mexer no resto da composição. */
  const releaseBackground = () => {
    if (backgroundId) {
      api.delete(`/thumbnail-preview/background/${backgroundId}`).catch(() => {})
    }
    setBackgroundId(null)
  }

  /** Descarta a composição inteira e volta ao estado inicial. */
  const discardAll = () => {
    if (!window.confirm('Descartar a composição e voltar ao estado inicial?')) return
    releaseBackground()
    // Invalida o que estiver em voo: a resposta que chegar depois disso é de
    // uma composição que não existe mais. Como o guard faz a resposta obsoleta
    // sair sem tocar em `loading`, o spinner tem que ser desligado aqui — senão
    // fica preso em "renderizando…" para sempre.
    reqId.current++
    setLoading(false)
    setS({ ...DEFAULT, elements: [newGradient(), newText()] })
    setPreviewUrl(''); setError(''); setWarnings([])
  }

  // --- manipulação da lista de elementos ---
  const updateElement = (id: string, patch: Partial<Element>) =>
    setS(p => ({
      ...p,
      elements: p.elements.map(el => (el.id === id ? { ...el, ...patch } as Element : el)),
    }))

  const updatePlacement = (id: string, patch: Partial<Placement>) =>
    setS(p => ({
      ...p,
      elements: p.elements.map(el =>
        el.id === id ? { ...el, placement: { ...el.placement, ...patch } } : el),
    }))

  const addElement = (type: ElementType) =>
    setS(p => ({
      ...p,
      elements: [...p.elements,
        type === 'gradient' ? newGradient() : type === 'text_box' ? newText() : newImage()],
    }))

  const removeElement = (id: string) =>
    setS(p => ({ ...p, elements: p.elements.filter(el => el.id !== id) }))

  /** Move um elemento na pilha. Índice maior = desenhado por cima. */
  const moveElement = (index: number, delta: number) =>
    setS(p => {
      const target = index + delta
      if (target < 0 || target >= p.elements.length) return p
      const elements = [...p.elements]
      const [item] = elements.splice(index, 1)
      elements.splice(target, 0, item)
      return { ...p, elements }
    })

  const fontOptions = useMemo(
    () => fonts.map(f => ({ value: f.path, label: `${f.family} · ${f.label}` })),
    [fonts],
  )

  const copyJson = async () => {
    await navigator.clipboard.writeText(
      JSON.stringify({ thumbnail: toThumbnailJson(s) }, null, 2))
    setCopied(true); setTimeout(() => setCopied(false), 1500)
  }

  const setSize = (preset: string) => {
    const [w, h] = preset.split('x').map(Number)
    setS(p => ({ ...p, width: w, height: h }))
  }

  const isPortrait = s.height > s.width
  const imgClass = isPortrait ? 'max-h-[72vh] w-auto' : 'w-full max-h-[72vh]'

  return (
    <Layout
      title="Preview de Thumbnail"
      description="Componha fundo + elementos e veja a thumbnail final"
    >
      <div className="grid grid-cols-1 lg:grid-cols-[440px_1fr] gap-6">
        {/* ----------------------------- Formulário ----------------------------- */}
        <div className="space-y-4 bg-navy-950/40 border border-navy-900 rounded-xl p-5 max-h-[80vh] overflow-y-auto">

          {/* Tamanho */}
          <div className="grid grid-cols-2 gap-3">
            <Select
              label="Tamanho" options={SIZE_PRESETS}
              value={`${s.width}x${s.height}`}
              onChange={v => setSize((v as string) ?? '1280x720')}
              isClearable={false} isSearchable={false}
            />
            <div className="grid grid-cols-2 gap-2">
              <FormField label="Largura" type="number" value={s.width}
                onChange={e => set('width', Number(e.target.value))} />
              <FormField label="Altura" type="number" value={s.height}
                onChange={e => set('height', Number(e.target.value))} />
            </div>
          </div>

          {/* --------------------------- Fundo --------------------------- */}
          <div className="space-y-3 pt-3 border-t border-navy-900">
            <p className="text-sm font-semibold text-navy-200">Fundo</p>

            {/* Segmentado em vez de select: são 3 opções fixas e a troca é
                frequente — um clique direto poupa abrir/fechar o menu. */}
            <div className="grid grid-cols-3 gap-1 p-1 rounded-lg bg-navy-950/60
                            border border-navy-900">
              {([
                { value: 'ai', label: 'IA', icon: <Sparkles size={12} /> },
                { value: 'image', label: 'Imagem', icon: <ImageIcon size={12} /> },
                { value: 'color', label: 'Cor', icon: <Blend size={12} /> },
              ] as const).map(opt => (
                <button
                  key={opt.value}
                  onClick={() => {
                    releaseBackground()
                    set('bg_type', opt.value as BackgroundType)
                  }}
                  className={`flex items-center justify-center gap-1.5 py-1.5 rounded-md
                              text-xs font-medium transition-colors
                    ${s.bg_type === opt.value
                      ? 'bg-navy-700 text-white'
                      : 'text-navy-400 hover:text-navy-100 hover:bg-navy-900'}`}
                >
                  {opt.icon}{opt.label}
                </button>
              ))}
            </div>

            {s.bg_type === 'ai' && (
              <>
                <div>
                  <label className="block text-xs font-medium text-navy-300 mb-1.5">
                    Prompt
                  </label>
                  <textarea
                    value={s.bg_prompt} rows={3}
                    onChange={e => set('bg_prompt', e.target.value)}
                    className="w-full border border-navy-700 rounded-lg px-3 py-2 text-sm text-white
                               placeholder-navy-500 focus:outline-none focus:border-navy-500 resize-y"
                    style={{ background: '#0d1117' }}
                  />
                </div>
                <FormField label="Modelo" value={s.bg_model}
                  onChange={e => set('bg_model', e.target.value)} />

                <div className="flex items-center gap-2">
                  <button
                    onClick={generateBackground} disabled={generatingBg}
                    className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm
                               font-medium bg-emerald-700 text-white hover:bg-emerald-600
                               disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    {generatingBg
                      ? <span className="h-3.5 w-3.5 rounded-full border-2 border-white/40
                                         border-t-white animate-spin" />
                      : <Sparkles size={15} />}
                    {generatingBg ? 'Gerando…' : backgroundId ? 'Gerar outro fundo' : 'Gerar fundo'}
                  </button>
                  {backgroundId && (
                    <button
                      onClick={releaseBackground} title="Descartar o fundo gerado"
                      className="px-3 py-2.5 rounded-lg text-sm bg-navy-800 text-navy-200
                                 hover:bg-navy-700 transition-colors"
                    >
                      <Trash2 size={15} />
                    </button>
                  )}
                </div>

                <Hint>
                  {backgroundId
                    ? 'Fundo fixado — os ajustes de texto reaproveitam esta imagem, sem gerar de novo. Clique em "Gerar outro fundo" para trocar.'
                    : 'Gerar o fundo é o passo caro; ele é feito uma vez e reaproveitado enquanto você ajusta os elementos.'}
                </Hint>
              </>
            )}

            {s.bg_type === 'image' && (
              <>
                <FormField
                  label="Caminho da imagem" value={s.bg_source}
                  placeholder="./assets/image/foto.jpg"
                  onChange={e => set('bg_source', e.target.value)}
                />
                <div className="grid grid-cols-2 gap-3">
                  <Select
                    label="Ajuste" isClearable={false} isSearchable={false}
                    options={[{ value: 'cover', label: 'cover' }, { value: 'contain', label: 'contain' }]}
                    value={s.bg_fit_mode}
                    onChange={v => set('bg_fit_mode', (v as string) ?? 'cover')}
                  />
                  <Select
                    label="Foco do corte" isClearable={false} isSearchable={false}
                    options={[{ value: 'center', label: 'centro' }, { value: 'face', label: 'rosto' }]}
                    value={s.bg_focus}
                    onChange={v => set('bg_focus', (v as string) ?? 'center')}
                  />
                </div>
                <Hint>Caminho relativo à pasta <code>videomaker/</code>.</Hint>
              </>
            )}

            {s.bg_type === 'color' && (
              <ColorPicker label="Cor" value={s.bg_color}
                onChange={v => set('bg_color', v)} />
            )}
          </div>

          {/* ------------------------- Elementos ------------------------- */}
          <div className="space-y-3 pt-3 border-t border-navy-900">
            <div className="flex items-center justify-between">
              <p className="text-sm font-semibold text-navy-200">
                Elementos <span className="text-navy-500 font-normal">({s.elements.length})</span>
              </p>
              <div className="flex gap-1">
                <AddButton icon={<Blend size={11} />} label="Degradê"
                  onClick={() => addElement('gradient')} />
                <AddButton icon={<Type size={11} />} label="Texto"
                  onClick={() => addElement('text_box')} />
                <AddButton icon={<ImageIcon size={11} />} label="Imagem"
                  onClick={() => addElement('image')} />
              </div>
            </div>
            <Hint>O último da lista é desenhado por cima dos demais.</Hint>

            {s.elements.map((el, i) => (
              <ElementCard
                key={el.id} el={el} index={i} total={s.elements.length}
                fontOptions={fontOptions}
                onMove={d => moveElement(i, d)}
                onRemove={() => removeElement(el.id)}
                onChange={patch => updateElement(el.id, patch)}
                onPlacement={patch => updatePlacement(el.id, patch)}
              />
            ))}

            {s.elements.length === 0 && (
              <p className="text-xs text-navy-500 py-3">
                Nenhum elemento — a thumbnail será só o fundo.
              </p>
            )}
          </div>

          {/* --------------------------- Ações --------------------------- */}
          <div className="flex gap-2 pt-2">
            <button
              onClick={copyJson}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm
                         font-medium bg-navy-800 text-white hover:bg-navy-700 transition-colors"
            >
              {copied ? <Check size={15} /> : <Copy size={15} />}
              {copied ? 'Copiado!' : 'Copiar JSON'}
            </button>
            <button
              onClick={discardAll} title="Descartar tudo e recomeçar"
              className="flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm
                         font-medium bg-red-950 text-red-300 border border-red-900
                         hover:bg-red-900 hover:text-red-100 transition-colors"
            >
              <RotateCcw size={15} />
              Descartar
            </button>
          </div>
        </div>

        {/* ------------------------------ Preview ------------------------------ */}
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-2 flex-wrap min-h-[28px]">
            <span className="text-xs font-medium text-navy-300 tabular-nums">
              {s.width}×{s.height}
            </span>

            {backgroundId && (
              <span className="flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full
                               bg-emerald-950/70 text-emerald-300 border border-emerald-900">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                fundo fixado
              </span>
            )}

            {(loading || generatingBg) && (
              <span className="flex items-center gap-1.5 text-[11px] text-navy-400">
                <span className="h-2.5 w-2.5 rounded-full border-2 border-navy-600
                                 border-t-navy-300 animate-spin" />
                {generatingBg ? 'gerando fundo…' : 'renderizando…'}
              </span>
            )}

            {error && (
              <span className="flex items-center gap-1 text-[11px] px-2 py-0.5 rounded
                               bg-red-950/60 text-red-300 border border-red-900">
                <AlertTriangle size={11} />{error}
              </span>
            )}

            {previewUrl && (
              <a
                href={previewUrl} download={`thumbnail-${s.width}x${s.height}.png`}
                className="ml-auto flex items-center gap-1.5 text-[11px] px-2.5 py-1 rounded-md
                           bg-navy-800/70 text-navy-200 border border-navy-800
                           hover:bg-navy-700 hover:text-white transition-colors"
              >
                <Download size={11} /> Baixar
              </a>
            )}
          </div>

          {warnings.length > 0 && (
            <div className="rounded-lg border border-amber-900 bg-amber-950/40 px-3 py-2">
              <div className="flex items-center gap-2 text-amber-300 text-xs font-medium mb-1">
                <AlertTriangle size={13} />
                A engine seguiu com um fallback
              </div>
              <ul className="text-[11px] leading-snug text-amber-200/80 space-y-0.5">
                {warnings.map((w, i) => <li key={i}>{w}</li>)}
              </ul>
            </div>
          )}

          {!canAutoPreview && !previewUrl && (
            <div className="rounded-lg border border-navy-800 bg-navy-950/40 px-3 py-2
                            text-xs text-navy-400">
              Clique em <b className="text-navy-200">Gerar fundo</b> para começar — assim a
              imagem de IA é criada uma vez só, e não a cada ajuste.
            </div>
          )}

          <div className="rounded-xl border border-navy-900 flex items-center justify-center
                          overflow-auto bg-black/40 p-4 min-h-[300px]">
            {previewUrl
              ? <img
                  src={previewUrl} alt="preview"
                  className={`${imgClass} object-contain rounded shadow-2xl
                              transition-opacity duration-200
                              ${loading ? 'opacity-60' : 'opacity-100'}`}
                />
              : <p className="text-sm text-navy-500 py-20">Sem preview</p>}
          </div>
        </div>
      </div>
    </Layout>
  )
}

// ----------------------------------------------------------------------
// Componentes auxiliares
// ----------------------------------------------------------------------

function Hint({ children }: { children: React.ReactNode }) {
  return <p className="text-[11px] leading-snug text-navy-500">{children}</p>
}

function AddButton({ icon, label, onClick }: {
  icon: React.ReactNode; label: string; onClick: () => void
}) {
  return (
    <button
      onClick={onClick} title={`Adicionar ${label}`}
      className="flex items-center gap-1 px-2 py-1 rounded-md text-[11px] font-medium
                 bg-navy-800/70 text-navy-300 border border-navy-800
                 hover:bg-navy-700 hover:text-white hover:border-navy-600
                 transition-colors"
    >
      <Plus size={10} />{icon}<span className="hidden sm:inline">{label}</span>
    </button>
  )
}

const ELEMENT_LABEL: Record<ElementType, string> = {
  gradient: 'Degradê', text_box: 'Texto', image: 'Imagem',
}

const ELEMENT_ICON: Record<ElementType, React.ReactNode> = {
  gradient: <Blend size={12} />,
  text_box: <Type size={12} />,
  image: <ImageIcon size={12} />,
}

const ANCHOR_X = [
  { value: 'left', label: 'esquerda' },
  { value: 'center', label: 'centro' },
  { value: 'right', label: 'direita' },
]
const ANCHOR_Y = [
  { value: 'top', label: 'topo' },
  { value: 'center', label: 'centro' },
  { value: 'bottom', label: 'base' },
]

function ElementCard({ el, index, total, fontOptions, onMove, onRemove, onChange, onPlacement }: {
  el: Element
  index: number
  total: number
  fontOptions: { value: string; label: string }[]
  onMove: (delta: number) => void
  onRemove: () => void
  onChange: (patch: Partial<Element>) => void
  onPlacement: (patch: Partial<Placement>) => void
}) {
  const [open, setOpen] = useState(true)

  const icon = ELEMENT_ICON[el.type]

  return (
    <div className={`rounded-lg border bg-navy-950/60 transition-colors
                     ${open ? 'border-navy-700' : 'border-navy-900 hover:border-navy-800'}`}>
      <div className="flex items-center gap-2 px-2.5 py-2">
        <button onClick={() => setOpen(o => !o)}
          className="flex items-center gap-2 flex-1 min-w-0 text-left group">
          <span className={`shrink-0 transition-transform ${open ? '' : '-rotate-90'}`}>
            <ChevronDown size={12} className="text-navy-500" />
          </span>
          <span className="shrink-0 text-navy-400">{icon}</span>
          <span className="text-xs font-medium text-navy-200 truncate group-hover:text-white">
            {ELEMENT_LABEL[el.type]}
            {el.type === 'text_box' && el.content && (
              <span className="text-navy-500 font-normal"> · {el.content.split('\n')[0]}</span>
            )}
            {el.type === 'image' && el.source && (
              <span className="text-navy-500 font-normal"> · {el.source.split('/').pop()}</span>
            )}
          </span>
        </button>

        <div className="flex items-center gap-0.5 shrink-0">
          <button onClick={() => onMove(-1)} disabled={index === 0}
            className="p-1 rounded text-navy-400 hover:text-white hover:bg-navy-800
                       disabled:opacity-20 disabled:hover:bg-transparent transition-colors"
            title="Descer na pilha">
            <ChevronUp size={13} />
          </button>
          <button onClick={() => onMove(1)} disabled={index === total - 1}
            className="p-1 rounded text-navy-400 hover:text-white hover:bg-navy-800
                       disabled:opacity-20 disabled:hover:bg-transparent transition-colors"
            title="Subir na pilha">
            <ChevronDown size={13} />
          </button>
          <button onClick={onRemove} title="Remover"
            className="p-1 rounded text-red-400/60 hover:text-red-300 hover:bg-red-950/50
                       transition-colors">
            <Trash2 size={13} />
          </button>
        </div>
      </div>

      {open && (
        <div className="px-3 pb-3 space-y-3 border-t border-navy-900 pt-3">
          {el.type === 'gradient' && (
            <GradientFields el={el} onChange={onChange} />
          )}
          {el.type === 'text_box' && (
            <TextFields el={el} fontOptions={fontOptions} onChange={onChange} />
          )}
          {el.type === 'image' && (
            <ImageFields el={el} onChange={onChange} />
          )}

          <PlacementFields p={el.placement} onChange={onPlacement} />
        </div>
      )}
    </div>
  )
}

function GradientFields({ el, onChange }: {
  el: GradientElement; onChange: (patch: Partial<GradientElement>) => void
}) {
  const updateStop = (i: number, patch: Partial<GradientStop>) =>
    onChange({ stops: el.stops.map((st, idx) => (idx === i ? { ...st, ...patch } : st)) })

  return (
    <>
      <Select
        label="Direção" isClearable={false} isSearchable={false}
        options={[
          { value: 'to_top', label: '↑ de baixo para cima' },
          { value: 'to_bottom', label: '↓ de cima para baixo' },
          { value: 'to_left', label: '← da direita para a esquerda' },
          { value: 'to_right', label: '→ da esquerda para a direita' },
        ]}
        value={el.direction}
        onChange={v => onChange({ direction: (v as GradientElement['direction']) ?? 'to_top' })}
      />

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <label className="text-xs font-medium text-navy-300">Paradas</label>
          <button
            onClick={() => onChange({ stops: [...el.stops, { color: '#000000', opacity: 0.5, at: 1 }] })}
            className="text-[11px] text-navy-300 hover:text-white flex items-center gap-1
                       px-1.5 py-0.5 rounded hover:bg-navy-800 transition-colors"
          >
            <Plus size={11} /> adicionar
          </button>
        </div>

        {el.stops.map((st, i) => (
          <div key={i} className="rounded-lg bg-navy-950/50 border border-navy-900 p-2.5 space-y-2.5">
            <div className="flex items-center gap-2">
              <ColorPicker value={st.color} compact
                onChange={v => updateStop(i, { color: v })} />
              <button
                onClick={() => onChange({ stops: el.stops.filter((_, idx) => idx !== i) })}
                disabled={el.stops.length <= 2}
                title="Remover parada"
                className="ml-auto text-red-400/70 hover:text-red-300 disabled:opacity-25
                           disabled:cursor-not-allowed shrink-0"
              >
                <Trash2 size={12} />
              </button>
            </div>
            <Slider label="Opacidade" value={st.opacity} min={0} max={1} step={0.05}
              onChange={v => updateStop(i, { opacity: v })} />
            <Slider label="Posição" value={st.at} min={0} max={1} step={0.05}
              onChange={v => updateStop(i, { at: v })} />
          </div>
        ))}
        <Hint>
          <b>Posição</b> vai de 0 a 1 na direção escolhida (0 = onde o degradê começa).
        </Hint>
      </div>
    </>
  )
}

function TextFields({ el, fontOptions, onChange }: {
  el: TextElement
  fontOptions: { value: string; label: string }[]
  onChange: (patch: Partial<TextElement>) => void
}) {
  return (
    <>
      <div>
        <label className="block text-xs font-medium text-navy-300 mb-1.5">
          Texto <span className="text-navy-500 font-normal">(Enter quebra a linha)</span>
        </label>
        <textarea
          value={el.content} rows={2}
          onChange={e => onChange({ content: e.target.value })}
          className="w-full border border-navy-700 rounded-lg px-3 py-2 text-sm text-white
                     focus:outline-none focus:border-navy-500 resize-y transition-colors"
          style={{ background: '#0d1117' }}
        />
      </div>

      <Select label="Fonte" options={fontOptions} value={el.font_path}
        onChange={v => onChange({ font_path: (v as string) ?? DEFAULT_FONT })} />

      <Slider label="Tamanho" value={el.font_size} min={16} max={280} step={2} unit="px"
        onChange={v => onChange({ font_size: v })} />

      <ColorPicker label="Cor do texto" value={el.text_color}
        onChange={v => onChange({ text_color: v })} />

      <div className="grid grid-cols-2 gap-3">
        <Select
          label="Alinhamento" isClearable={false} isSearchable={false}
          options={[
            { value: 'left', label: 'esquerda' },
            { value: 'center', label: 'centro' },
            { value: 'right', label: 'direita' },
          ]}
          value={el.align}
          onChange={v => onChange({ align: (v as TextElement['align']) ?? 'left' })}
        />
        <Slider label="Entrelinha" value={el.line_spacing} min={0.7} max={2} step={0.05}
          onChange={v => onChange({ line_spacing: v })} />
      </div>

      <div className="pt-1 border-t border-navy-900 space-y-2.5">
        <Toggle label="Contorno" checked={el.stroke_enabled}
          onChange={v => onChange({ stroke_enabled: v })} />
        {el.stroke_enabled && (
          <div className="space-y-2.5 pl-1">
            <ColorPicker label="Cor do contorno" value={el.stroke_color} compact
              onChange={v => onChange({ stroke_color: v })} />
            <Slider label="Espessura" value={el.stroke_width} min={0} max={30} step={1} unit="px"
              onChange={v => onChange({ stroke_width: v })} />
          </div>
        )}
      </div>

      <div className="pt-1 border-t border-navy-900 space-y-2.5">
        <Toggle label="Sombra" checked={el.shadow_enabled}
          onChange={v => onChange({ shadow_enabled: v })} />
        {el.shadow_enabled && (
          <div className="space-y-2.5 pl-1">
            <ColorPicker label="Cor da sombra" value={el.shadow_color} compact
              onChange={v => onChange({ shadow_color: v })} />
            <Slider label="Opacidade" value={el.shadow_opacity} min={0} max={1} step={0.05}
              onChange={v => onChange({ shadow_opacity: v })} />
            <Slider label="Desfoque" value={el.shadow_blur} min={0} max={40} step={1} unit="px"
              onChange={v => onChange({ shadow_blur: v })} />
            <div className="grid grid-cols-2 gap-3">
              <Slider label="Deslocamento X" value={el.shadow_offset[0]} min={-40} max={40} step={1}
                onChange={v => onChange({ shadow_offset: [v, el.shadow_offset[1]] })} />
              <Slider label="Deslocamento Y" value={el.shadow_offset[1]} min={-40} max={40} step={1}
                onChange={v => onChange({ shadow_offset: [el.shadow_offset[0], v] })} />
            </div>
          </div>
        )}
      </div>
    </>
  )
}

function ImageFields({ el, onChange }: {
  el: ImageElement; onChange: (patch: Partial<ImageElement>) => void
}) {
  return (
    <>
      <FormField
        label="Caminho" value={el.source}
        placeholder="./assets/image/logo.png"
        onChange={e => onChange({ source: e.target.value })}
      />
      <Slider label="Cantos arredondados" value={el.border_radius} min={0} max={120} step={2} unit="px"
        onChange={v => onChange({ border_radius: v })} />
      <Slider label="Opacidade" value={el.opacity} min={0} max={1} step={0.05}
        onChange={v => onChange({ opacity: v })} />
      <Hint>Caminho relativo à pasta <code>videomaker/</code>.</Hint>
    </>
  )
}

function PlacementFields({ p, onChange }: {
  p: Placement; onChange: (patch: Partial<Placement>) => void
}) {
  return (
    <div className="space-y-3 pt-3 border-t border-navy-900">
      <label className="text-xs font-medium text-navy-300">Posição</label>

      {/* Grade 3x3 de ancoragem: mais rápida de ler que dois selects. */}
      <div className="flex items-start gap-3">
        <div className="grid grid-cols-3 gap-1 shrink-0">
          {ANCHOR_Y.map(y => ANCHOR_X.map(x => {
            const active = p.anchor_x === x.value && p.anchor_y === y.value
            return (
              <button
                key={`${x.value}-${y.value}`}
                type="button"
                title={`${x.label} · ${y.label}`}
                onClick={() => onChange({ anchor_x: x.value, anchor_y: y.value })}
                className={`h-6 w-6 rounded border transition-colors
                  ${active
                    ? 'bg-navy-500 border-navy-400'
                    : 'bg-navy-950 border-navy-800 hover:border-navy-600'}`}
              >
                <span className={`block mx-auto h-1.5 w-1.5 rounded-full
                  ${active ? 'bg-white' : 'bg-navy-700'}`} />
              </button>
            )
          }))}
        </div>

        <div className="flex-1 min-w-0 space-y-2.5">
          <Slider label="Largura" value={p.width} min={0} max={100} step={1} unit="%"
            onChange={v => onChange({ width: v })} />
          <Slider label="Altura" value={p.height} min={0} max={100} step={1} unit="%"
            onChange={v => onChange({ height: v })} />
        </div>
      </div>

      <Toggle
        label="Ocupar a tela inteira"
        hint="Desligado, as medidas valem sobre a área segura (dentro das margens)."
        checked={p.full_screen}
        onChange={v => onChange({ full_screen: v })}
      />
      <Hint>Largura/altura em <b>0%</b> = não declarar (mantém o tamanho natural).</Hint>
    </div>
  )
}
