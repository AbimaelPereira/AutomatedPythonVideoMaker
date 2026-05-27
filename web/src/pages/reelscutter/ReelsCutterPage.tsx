import { useState } from 'react'
import Layout from '../../components/Layout'
import StepUrl from './steps/StepUrl'
import StepTranscript from './steps/StepTranscript'
import StepConfig from './steps/StepConfig'
import StepReview from './steps/StepReview'
import StepEdit from './steps/StepEdit'
import StepResult from './steps/StepResult'
import { Check } from 'lucide-react'

const STEPS = ['URL', 'Transcrição', 'Configuração', 'Curadoria', 'Edição', 'Resultado']

export interface ReelsState {
  url: string
  video_id: string
  transcript: { text: string; start: number; duration: number }[]
  transcription_text: string
  config: {
    min_words: number
    max_words: number
    min_duration: number
    max_duration: number
    channel_name: string
  }
  audio_path: string
  clips: any[]
  selected_clips: any[]
  results: any[]
  json_path: string
}

const DEFAULT_CONFIG = {
  min_words:    12,
  max_words:    18,
  min_duration: 55,
  max_duration: 85,
  channel_name: 'devocional_com_jesus',
}

export default function ReelsCutterPage() {
  const [step, setStep] = useState(0)
  const [state, setState] = useState<ReelsState>({
    url: '', video_id: '', transcript: [], transcription_text: '',
    config: DEFAULT_CONFIG,
    audio_path: '', clips: [], selected_clips: [], results: [], json_path: '',
  })

  function update(patch: Partial<ReelsState>) {
    setState(s => ({ ...s, ...patch }))
  }

  function next() { setStep(s => s + 1) }
  function back() { setStep(s => s - 1) }

  return (
    <Layout title="ReelsCutter" description="Pipeline de criação de clips virais">
      {/* Stepper */}
      <div className="flex items-center gap-0 mb-8 overflow-x-auto pb-2">
        {STEPS.map((label, i) => (
          <div key={i} className="flex items-center">
            <div className="flex flex-col items-center gap-1.5">
              <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold border-2 transition-colors ${
                i < step  ? 'bg-emerald-600 border-emerald-600 text-white'
                : i === step ? 'bg-navy-600 border-navy-500 text-white'
                : 'bg-transparent border-navy-700 text-navy-600'
              }`}>
                {i < step ? <Check size={14} /> : i + 1}
              </div>
              <span className={`text-xs whitespace-nowrap ${
                i === step ? 'text-white font-medium' : i < step ? 'text-emerald-400' : 'text-navy-600'
              }`}>
                {label}
              </span>
            </div>
            {i < STEPS.length - 1 && (
              <div className={`w-12 h-0.5 mb-5 mx-1 transition-colors ${i < step ? 'bg-emerald-600' : 'bg-navy-800'}`} />
            )}
          </div>
        ))}
      </div>

      {/* Step content */}
      <div className="rounded-xl border border-navy-800 p-6 lg:p-8" style={{ background: '#141920' }}>
        {step === 0 && <StepUrl      state={state} update={update} onNext={next} />}
        {step === 1 && <StepTranscript state={state} onNext={next} onBack={back} />}
        {step === 2 && <StepConfig   state={state} update={update} onNext={next} onBack={back} />}
        {step === 3 && <StepReview   state={state} update={update} onNext={next} onBack={back} />}
        {step === 4 && <StepEdit     state={state} update={update} onNext={next} onBack={back} />}
        {step === 5 && <StepResult   state={state} onBack={back} />}
      </div>
    </Layout>
  )
}
