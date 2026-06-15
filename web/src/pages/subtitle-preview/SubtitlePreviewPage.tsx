import { useEffect, useMemo, useRef, useState } from 'react'
import Layout from '../../components/Layout'
import FormField from '../../components/ui/FormField'
import Switch from '../../components/ui/Switch'
import Select from '../../components/ui/Select'
import { api } from '../../services/api'
import { useDebouncedValue } from '../../hooks/useDebouncedValue'
import { Copy, Check, Plus, Trash2 } from 'lucide-react'

interface FontOption { path: string; label: string; family: string }

// uppercase: 'herdar' = usa o global; 'sim'/'nao' = força para este estilo.
type CaseMode = 'herdar' | 'sim' | 'nao'

interface PaletteItem {
  font_path: string
  fill: string
  uppercase: CaseMode
  stroke_enabled: boolean
  stroke: string
  stroke_width: number
  shadow_enabled: boolean
  shadow_color: string
  shadow_opacity: number
  shadow_blur: number
  shadow_offset: [number, number]
}

interface State {
  type: 'classic' | 'karaoke'
  text: string
  output_ratio: '9:16' | '16:9'
  uppercase: boolean
  // posicionamento
  use_placement: boolean
  anchor_x: string
  anchor_y: string
  region: string
  subtitle_position: 'top' | 'center' | 'bottom'
  padding_side: number
  padding_top: number
  padding_bottom: number
  background_color: string
  // classic
  font_path: string
  font_size: number
  color: string
  stroke_enabled: boolean
  stroke_color: string
  stroke_width: number
  shadow_enabled: boolean
  shadow_color: string
  shadow_opacity: number
  blur_radius: number
  shadow_offset: [number, number]
  // karaoke
  palette: PaletteItem[]
  words_per_group: number
  layout: 'one_per_line' | 'fill_line'
  use_line_mode: boolean
  min_chars_per_line: number
  line_fill_ratio: number
  lines_per_group: number
}

const DEFAULT_FONT = './assets/fonts/Montserrat/Montserrat-Black.ttf'

const newPaletteItem = (fill = '#FFFFFF'): PaletteItem => ({
  font_path: DEFAULT_FONT, fill, uppercase: 'herdar',
  stroke_enabled: true, stroke: '#000000', stroke_width: 3,
  shadow_enabled: false, shadow_color: '#000000', shadow_opacity: 0.85,
  shadow_blur: 6, shadow_offset: [4, 4],
})

const DEFAULT: State = {
  type: 'classic',
  text: 'O segredo que ninguém te contou',
  output_ratio: '9:16',
  uppercase: true,
  use_placement: false,
  anchor_x: 'center', anchor_y: 'bottom', region: '',
  subtitle_position: 'bottom',
  padding_side: 50, padding_top: 100, padding_bottom: 850,
  background_color: '#101418',
  font_path: './assets/fonts/Poppins/Poppins-Black.ttf',
  font_size: 70, color: '#ffffff',
  stroke_enabled: true, stroke_color: '#000000', stroke_width: 3,
  shadow_enabled: false, shadow_color: '#000000', shadow_opacity: 0.8,
  blur_radius: 6, shadow_offset: [4, 4],
  palette: [newPaletteItem('#FFFFFF'), newPaletteItem('#1beb0c')],
  words_per_group: 4, layout: 'one_per_line',
  use_line_mode: false, min_chars_per_line: 10, line_fill_ratio: 0.85, lines_per_group: 3,
}

const PADDINGS_DEFAULT: Record<string, { side: number; top: number; bottom: number }> = {
  '9:16': { side: 50, top: 100, bottom: 850 },
  '16:9': { side: 96, top: 54, bottom: 54 },
}

/** CaseMode → bool|null para a API (None = herda o global). */
const caseToApi = (m: CaseMode): boolean | null => (m === 'herdar' ? null : m === 'sim')

/** Converte o State no payload aceito pelo endpoint. */
function toPayload(s: State) {
  return {
    type: s.type, text: s.text, output_ratio: s.output_ratio, uppercase: s.uppercase,
    use_placement: s.use_placement,
    placement: { anchor: [s.anchor_x, s.anchor_y], region: s.region || null },
    subtitle_position: s.subtitle_position,
    padding_side: s.padding_side, padding_top: s.padding_top, padding_bottom: s.padding_bottom,
    background_color: s.background_color,
    font_path: s.font_path, font_size: s.font_size, color: s.color,
    stroke_enabled: s.stroke_enabled, stroke_color: s.stroke_color, stroke_width: s.stroke_width,
    shadow_enabled: s.shadow_enabled, shadow_color: s.shadow_color, shadow_opacity: s.shadow_opacity,
    blur_radius: s.blur_radius, shadow_offset: s.shadow_offset,
    palette: s.palette.map(p => ({
      font_path: p.font_path, fill: p.fill, uppercase: caseToApi(p.uppercase),
      stroke_enabled: p.stroke_enabled, stroke: p.stroke, stroke_width: p.stroke_width,
      shadow_enabled: p.shadow_enabled, shadow_color: p.shadow_color,
      shadow_opacity: p.shadow_opacity, shadow_blur: p.shadow_blur, shadow_offset: p.shadow_offset,
    })),
    words_per_group: s.words_per_group, layout: s.layout,
    min_chars_per_line: s.use_line_mode ? s.min_chars_per_line : null,
    line_fill_ratio: s.use_line_mode ? s.line_fill_ratio : null,
    lines_per_group: s.lines_per_group,
  }
}

/** Bloco `subtitle` pronto para colar no JSON do canal. */
function toSubtitleJson(s: State) {
  const placement = s.use_placement
    ? { placement: { anchor: [s.anchor_x, s.anchor_y], ...(s.region && { region: s.region }) } }
    : { subtitle_position: s.subtitle_position }
  if (s.type === 'karaoke') {
    return {
      enabled: true, type: 'karaoke', uppercase: s.uppercase,
      ...(s.use_line_mode
        ? { min_chars_per_line: s.min_chars_per_line, line_fill_ratio: s.line_fill_ratio, lines_per_group: s.lines_per_group }
        : { words_per_group: s.words_per_group, layout: s.layout }),
      palette: s.palette.map(p => ({
        font_path: p.font_path,
        fill: p.fill,
        ...(p.uppercase !== 'herdar' && { uppercase: p.uppercase === 'sim' }),
        ...(p.stroke_enabled && { stroke: p.stroke, stroke_width: p.stroke_width }),
        ...(p.shadow_enabled && { shadow: { color: p.shadow_color, opacity: p.shadow_opacity, blur: p.shadow_blur, offset: p.shadow_offset } }),
      })),
      ...placement,
    }
  }
  return {
    enabled: true, type: 'classic', font_path: s.font_path, font_size: s.font_size,
    color: s.color, uppercase: s.uppercase,
    stroke_enabled: s.stroke_enabled, stroke_color: s.stroke_color, stroke_width: s.stroke_width,
    shadow_enabled: s.shadow_enabled,
    ...(s.shadow_enabled && { shadow_color: s.shadow_color, shadow_opacity: s.shadow_opacity, blur_radius: s.blur_radius, shadow_offset: s.shadow_offset }),
    ...placement,
  }
}

export default function SubtitlePreviewPage() {
  const [s, setS] = useState<State>(DEFAULT)
  const [fonts, setFonts] = useState<FontOption[]>([])
  const [previewUrl, setPreviewUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState(false)

  const debounced = useDebouncedValue(s, 250)
  const reqId = useRef(0)

  const set = <K extends keyof State>(k: K, v: State[K]) => setS(p => ({ ...p, [k]: v }))

  useEffect(() => {
    api.get<FontOption[]>('/subtitle-preview/fonts').then(r => setFonts(r.data)).catch(() => setFonts([]))
  }, [])

  // Recebe o PNG como ArrayBuffer → data URL base64 (sem blob/createObjectURL).
  // Um contador de request garante que só a resposta mais recente é aplicada.
  const fetchPreview = (payloadState: State) => {
    const id = ++reqId.current
    setLoading(true); setError('')
    api.post('/subtitle-preview', toPayload(payloadState), { responseType: 'arraybuffer' })
      .then(r => {
        if (id !== reqId.current) return
        const bytes = new Uint8Array(r.data)
        let bin = ''
        for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i])
        setPreviewUrl(`data:image/png;base64,${btoa(bin)}`)
        setLoading(false)
      })
      .catch(err => {
        if (id !== reqId.current) return
        const status = err?.response?.status
        if (status === 401) {
          setError('Sessão expirada — faça logout e login novamente.')
        } else {
          let msg = 'Falha ao gerar preview'
          try {
            const buf = err?.response?.data
            if (buf) msg = JSON.parse(new TextDecoder().decode(buf))?.detail ?? msg
          } catch { /* mantém genérico */ }
          setError(msg)
        }
        setLoading(false)
      })
  }

  // Renderiza o preview a cada mudança (debounced).
  useEffect(() => { fetchPreview(debounced) }, [debounced])

  const fontOptions = useMemo(
    () => fonts.map(f => ({ value: f.path, label: `${f.family} · ${f.label}` })),
    [fonts],
  )

  const setRatio = (ratio: '9:16' | '16:9') => {
    const p = PADDINGS_DEFAULT[ratio]
    setS(prev => ({ ...prev, output_ratio: ratio, padding_side: p.side, padding_top: p.top, padding_bottom: p.bottom }))
  }

  const updatePalette = (i: number, patch: Partial<PaletteItem>) =>
    setS(prev => ({ ...prev, palette: prev.palette.map((it, idx) => idx === i ? { ...it, ...patch } : it) }))
  const addPalette = () => setS(prev => ({ ...prev, palette: [...prev.palette, newPaletteItem('#ffcc00')] }))
  const removePalette = (i: number) => setS(prev => ({ ...prev, palette: prev.palette.filter((_, idx) => idx !== i) }))

  const copyJson = async () => {
    await navigator.clipboard.writeText(JSON.stringify({ subtitle: toSubtitleJson(s) }, null, 2))
    setCopied(true); setTimeout(() => setCopied(false), 1500)
  }

  const imgClass = s.output_ratio === '9:16'
    ? 'max-h-[72vh] w-auto'   // vertical: limita pela altura
    : 'w-full max-h-[72vh]'   // horizontal: ocupa a largura

  return (
    <Layout title="Preview de Legendas" description="Monte o estilo da legenda e veja em tempo real">
      <div className="grid grid-cols-1 lg:grid-cols-[420px_1fr] gap-6">
        {/* Formulário */}
        <div className="space-y-4 bg-navy-950/40 border border-navy-900 rounded-xl p-5 max-h-[80vh] overflow-y-auto">
          {/* Tipo + ratio */}
          <div className="grid grid-cols-2 gap-3">
            <Select label="Tipo" options={[{ value: 'classic', label: 'Classic' }, { value: 'karaoke', label: 'Karaokê' }]}
              value={s.type} onChange={v => set('type', (v as State['type']) ?? 'classic')} isClearable={false} isSearchable={false} />
            <Select label="Orientação" options={[{ value: '9:16', label: '9:16 (vertical)' }, { value: '16:9', label: '16:9 (horizontal)' }]}
              value={s.output_ratio} onChange={v => setRatio((v as State['output_ratio']) ?? '9:16')} isClearable={false} isSearchable={false} />
          </div>

          <FormField label="Texto de exemplo" value={s.text} onChange={e => set('text', e.target.value)} />
          <Switch label="Maiúsculas (geral)" description="Aplica a toda a legenda. No karaokê, cada estilo pode sobrescrever."
            checked={s.uppercase} onChange={v => set('uppercase', v)} />

          {/* ---------- CLASSIC ---------- */}
          {s.type === 'classic' && (
            <div className="space-y-3 pt-2 border-t border-navy-900">
              <Select label="Fonte" options={fontOptions} value={s.font_path}
                onChange={v => set('font_path', (v as string) ?? DEFAULT.font_path)} placeholder="Selecione..." />
              <FormField label="Tamanho da fonte" type="number" value={s.font_size} onChange={e => set('font_size', Number(e.target.value))} />
              <ColorRow label="Cor do texto" value={s.color} onChange={v => set('color', v)} />

              <Switch label="Contorno (stroke)" checked={s.stroke_enabled} onChange={v => set('stroke_enabled', v)} />
              {s.stroke_enabled && (
                <div className="grid grid-cols-2 gap-3">
                  <ColorRow label="Cor" value={s.stroke_color} onChange={v => set('stroke_color', v)} />
                  <FormField label="Espessura" type="number" value={s.stroke_width} onChange={e => set('stroke_width', Number(e.target.value))} />
                </div>
              )}

              <Switch label="Sombra" checked={s.shadow_enabled} onChange={v => set('shadow_enabled', v)} />
              {s.shadow_enabled && (
                <>
                  <ColorRow label="Cor da sombra" value={s.shadow_color} onChange={v => set('shadow_color', v)} />
                  <div className="grid grid-cols-2 gap-3">
                    <FormField label="Opacidade (0–1)" type="number" step="0.05" value={s.shadow_opacity} onChange={e => set('shadow_opacity', Number(e.target.value))} />
                    <FormField label="Desfoque (blur)" type="number" step="0.5" value={s.blur_radius} onChange={e => set('blur_radius', Number(e.target.value))} />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <FormField label="Offset X" type="number" value={s.shadow_offset[0]} onChange={e => set('shadow_offset', [Number(e.target.value), s.shadow_offset[1]])} />
                    <FormField label="Offset Y" type="number" value={s.shadow_offset[1]} onChange={e => set('shadow_offset', [s.shadow_offset[0], Number(e.target.value)])} />
                  </div>
                </>
              )}
            </div>
          )}

          {/* ---------- KARAOKE ---------- */}
          {s.type === 'karaoke' && (
            <div className="space-y-3 pt-2 border-t border-navy-900">
              <Switch label="Agrupar por linhas"
                description="Junta as palavras em linhas (em vez de uma por linha). Indicado para frases."
                checked={s.use_line_mode} onChange={v => set('use_line_mode', v)} />

              {s.use_line_mode ? (
                <div className="space-y-3">
                  <div className="grid grid-cols-3 gap-3">
                    <FormField label="Mín. de letras por linha" type="number" value={s.min_chars_per_line} onChange={e => set('min_chars_per_line', Number(e.target.value))} />
                    <FormField label="Largura máx. da linha" type="number" step="0.05" min="0" max="1" value={s.line_fill_ratio} onChange={e => set('line_fill_ratio', Number(e.target.value))} />
                    <FormField label="Linhas por tela" type="number" value={s.lines_per_group} onChange={e => set('lines_per_group', Number(e.target.value))} />
                  </div>
                  <Hint>Uma linha só fecha depois de atingir o <b>mín. de letras</b> (evita palavra solta) e quando a próxima palavra passaria da <b>largura máx.</b> (0,85 = 85% da faixa). <b>Linhas por tela</b> = quantas linhas aparecem antes de limpar. Aqui cada <b>estilo da paleta</b> colore uma linha inteira.</Hint>
                </div>
              ) : (
                <div className="space-y-3">
                  <div className="grid grid-cols-2 gap-3">
                    <FormField label="Palavras por tela" type="number" value={s.words_per_group} onChange={e => set('words_per_group', Number(e.target.value))} />
                    <Select label="Disposição"
                      options={[{ value: 'one_per_line', label: 'Uma palavra por linha' }, { value: 'fill_line', label: 'Encher a linha' }]}
                      value={s.layout} onChange={v => set('layout', (v as State['layout']) ?? 'one_per_line')} isClearable={false} isSearchable={false} />
                  </div>
                  <Hint><b>Palavras por tela</b> = quantas aparecem antes de limpar. <b>Uma palavra por linha</b> empilha cada palavra; <b>Encher a linha</b> coloca várias lado a lado até caber. Aqui cada <b>estilo da paleta</b> colore uma palavra (em rotação).</Hint>
                </div>
              )}

              {/* Paleta */}
              <div className="flex items-center justify-between pt-2">
                <div>
                  <p className="text-sm font-medium text-navy-200">Estilos da paleta ({s.palette.length})</p>
                  <p className="text-[11px] text-navy-500">As cores se alternam {s.use_line_mode ? 'a cada linha' : 'a cada palavra'}.</p>
                </div>
                <button onClick={addPalette} className="flex items-center gap-1 text-xs text-navy-300 hover:text-white px-2 py-1 rounded bg-navy-800 hover:bg-navy-700">
                  <Plus size={13} /> Adicionar
                </button>
              </div>

              {s.palette.map((p, i) => (
                <div key={i} className="border border-navy-800 rounded-lg p-3 space-y-3 bg-navy-950/40">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-navy-300">Estilo {i + 1}</span>
                    {s.palette.length > 1 && (
                      <button onClick={() => removePalette(i)} className="text-navy-500 hover:text-red-400" title="Remover estilo"><Trash2 size={14} /></button>
                    )}
                  </div>

                  <Select label="Fonte" options={fontOptions} value={p.font_path}
                    onChange={v => updatePalette(i, { font_path: (v as string) ?? DEFAULT_FONT })} placeholder="Fonte..." />
                  <ColorRow label="Cor do texto" value={p.fill} onChange={v => updatePalette(i, { fill: v })} />

                  <Select label="Maiúsculas neste estilo"
                    options={[{ value: 'herdar', label: 'Herdar do geral' }, { value: 'sim', label: 'Sempre MAIÚSCULAS' }, { value: 'nao', label: 'Manter como está' }]}
                    value={p.uppercase} onChange={v => updatePalette(i, { uppercase: (v as CaseMode) ?? 'herdar' })} isClearable={false} isSearchable={false} />

                  {/* Contorno */}
                  <Switch label="Contorno" checked={p.stroke_enabled} onChange={v => updatePalette(i, { stroke_enabled: v })} />
                  {p.stroke_enabled && (
                    <div className="grid grid-cols-2 gap-2">
                      <ColorRow label="Cor" value={p.stroke} onChange={v => updatePalette(i, { stroke: v })} />
                      <FormField label="Espessura" type="number" value={p.stroke_width} onChange={e => updatePalette(i, { stroke_width: Number(e.target.value) })} />
                    </div>
                  )}

                  {/* Sombra */}
                  <Switch label="Sombra" checked={p.shadow_enabled} onChange={v => updatePalette(i, { shadow_enabled: v })} />
                  {p.shadow_enabled && (
                    <>
                      <ColorRow label="Cor da sombra" value={p.shadow_color} onChange={v => updatePalette(i, { shadow_color: v })} />
                      <div className="grid grid-cols-2 gap-2">
                        <FormField label="Opacidade (0–1)" type="number" step="0.05" min="0" max="1" value={p.shadow_opacity} onChange={e => updatePalette(i, { shadow_opacity: Number(e.target.value) })} />
                        <FormField label="Desfoque" type="number" step="0.5" min="0" value={p.shadow_blur} onChange={e => updatePalette(i, { shadow_blur: Number(e.target.value) })} />
                      </div>
                    </>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* ---------- POSICIONAMENTO ---------- */}
          <div className="space-y-3 pt-2 border-t border-navy-900">
            <p className="text-sm font-semibold text-navy-200">Posição na tela</p>
            <Switch label="Posicionamento avançado"
              description="Ligado: ancore livremente e limite a largura. Desligado: só topo/centro/base."
              checked={s.use_placement} onChange={v => set('use_placement', v)} />
            {s.use_placement ? (
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <Select label="Horizontal" options={[{ value: 'left', label: 'Esquerda' }, { value: 'center', label: 'Centro' }, { value: 'right', label: 'Direita' }]}
                    value={s.anchor_x} onChange={v => set('anchor_x', (v as string) ?? 'center')} isClearable={false} isSearchable={false} />
                  <Select label="Vertical" options={[{ value: 'top', label: 'Topo' }, { value: 'center', label: 'Centro' }, { value: 'bottom', label: 'Base' }]}
                    value={s.anchor_y} onChange={v => set('anchor_y', (v as string) ?? 'center')} isClearable={false} isSearchable={false} />
                </div>
                <FormField label="Largura da faixa de texto (ex.: 30%)" placeholder="vazio = área toda" value={s.region} onChange={e => set('region', e.target.value)} />
                <Hint>A legenda fica dentro de uma faixa. <b>Largura da faixa</b> limita quanto ela ocupa (ex.: 30% deixa o texto estreito num canto). Vazio = usa toda a área segura.</Hint>
              </div>
            ) : (
              <Select label="Posição vertical" options={[{ value: 'top', label: 'Topo' }, { value: 'center', label: 'Centro' }, { value: 'bottom', label: 'Base' }]}
                value={s.subtitle_position} onChange={v => set('subtitle_position', (v as State['subtitle_position']) ?? 'bottom')} isClearable={false} isSearchable={false} />
            )}
            <div>
              <p className="text-xs font-medium text-navy-300 mb-1.5">Margem segura (px)</p>
              <div className="grid grid-cols-3 gap-3">
                <FormField label="Laterais" type="number" value={s.padding_side} onChange={e => set('padding_side', Number(e.target.value))} />
                <FormField label="Topo" type="number" value={s.padding_top} onChange={e => set('padding_top', Number(e.target.value))} />
                <FormField label="Base" type="number" value={s.padding_bottom} onChange={e => set('padding_bottom', Number(e.target.value))} />
              </div>
              <Hint>Margem livre nas bordas onde o texto pode ficar. Valores maiores afastam a legenda das bordas.</Hint>
            </div>
          </div>

          <button onClick={copyJson}
            className="w-full flex items-center justify-center gap-2 mt-2 px-4 py-2.5 rounded-lg text-sm font-medium bg-navy-800 text-white hover:bg-navy-700 transition-colors">
            {copied ? <Check size={15} /> : <Copy size={15} />}
            {copied ? 'Copiado!' : 'Copiar JSON do subtitle'}
          </button>
        </div>

        {/* Preview */}
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-3 flex-wrap">
            <span className="text-xs font-medium text-navy-300">Fundo</span>
            <input type="color" value={s.background_color} onChange={e => set('background_color', e.target.value)}
              className="h-7 w-10 rounded border border-navy-700 bg-transparent cursor-pointer" />
            {loading && <span className="text-xs text-navy-400">renderizando…</span>}
            {error && <span className="text-xs text-red-400">{error}</span>}
          </div>

          <div className="rounded-xl border border-navy-900 flex items-center justify-center overflow-auto bg-black/40 p-4 min-h-[300px]">
            {previewUrl
              ? <img src={previewUrl} alt="preview" className={`${imgClass} object-contain rounded`} />
              : <p className="text-sm text-navy-500 py-20">Sem preview</p>}
          </div>
        </div>
      </div>
    </Layout>
  )
}

/** Texto de ajuda curto abaixo de um campo/grupo. */
function Hint({ children }: { children: React.ReactNode }) {
  return <p className="text-[11px] leading-snug text-navy-500">{children}</p>
}

function ColorRow({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div>
      <label className="block text-xs font-medium text-navy-300 mb-1.5">{label}</label>
      <div className="flex items-center gap-2">
        <input type="color" value={value} onChange={e => onChange(e.target.value)}
          className="h-9 w-10 shrink-0 rounded border border-navy-700 bg-transparent cursor-pointer" />
        <input type="text" value={value} onChange={e => onChange(e.target.value)}
          className="w-full min-w-0 border border-navy-700 rounded-lg px-2 py-2 text-sm text-white focus:outline-none focus:border-navy-500"
          style={{ background: '#0d1117' }} />
      </div>
    </div>
  )
}
