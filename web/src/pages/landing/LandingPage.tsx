import { useEffect, useRef, useState } from 'react'
import { Scissors, Layers, Zap, Globe, ArrowRight, Play, ChevronDown } from 'lucide-react'

// ---------- helpers ----------

function useInView(threshold = 0.15) {
  const ref = useRef<HTMLDivElement>(null)
  const [visible, setVisible] = useState(false)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const obs = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) setVisible(true) },
      { threshold }
    )
    obs.observe(el)
    return () => obs.disconnect()
  }, [threshold])
  return { ref, visible }
}

function FadeIn({ children, delay = 0, className = '' }: { children: React.ReactNode; delay?: number; className?: string }) {
  const { ref, visible } = useInView()
  return (
    <div
      ref={ref}
      className={className}
      style={{
        opacity: visible ? 1 : 0,
        transform: visible ? 'translateY(0)' : 'translateY(28px)',
        transition: `opacity 0.6s ease ${delay}ms, transform 0.6s ease ${delay}ms`,
      }}
    >
      {children}
    </div>
  )
}

// ---------- sections ----------

function Navbar() {
  const [scrolled, setScrolled] = useState(false)
  useEffect(() => {
    const handler = () => setScrolled(window.scrollY > 40)
    window.addEventListener('scroll', handler)
    return () => window.removeEventListener('scroll', handler)
  }, [])

  return (
    <header
      className="fixed top-0 left-0 right-0 z-50 transition-all duration-300"
      style={{
        background: scrolled ? 'rgba(10,21,48,0.85)' : 'transparent',
        backdropFilter: scrolled ? 'blur(16px)' : 'none',
        borderBottom: scrolled ? '1px solid rgba(61,92,168,0.2)' : '1px solid transparent',
      }}
    >
      <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-navy-500 to-navy-700 flex items-center justify-center">
            <Scissors size={14} className="text-white" />
          </div>
          <span className="font-semibold text-navy-50 tracking-tight">Anonimo</span>
        </div>
        <nav className="hidden md:flex items-center gap-8 text-sm text-navy-200">
          <a href="#features" className="hover:text-white transition-colors">Features</a>
          <a href="#how" className="hover:text-white transition-colors">Como funciona</a>
          <a href="#pricing" className="hover:text-white transition-colors">Preços</a>
        </nav>
        <a
          href="/login"
          className="text-sm px-4 py-2 rounded-lg border border-navy-600 text-navy-200 hover:border-navy-400 hover:text-white transition-all"
        >
          Entrar
        </a>
      </div>
    </header>
  )
}

function Hero() {
  return (
    <section className="relative min-h-screen flex flex-col items-center justify-center overflow-hidden px-6 pt-16">
      {/* gradient blobs */}
      <div
        className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] rounded-full pointer-events-none"
        style={{
          background: 'radial-gradient(circle, rgba(61,92,168,0.18) 0%, transparent 70%)',
          filter: 'blur(40px)',
        }}
      />
      <div
        className="absolute bottom-0 right-1/4 w-[400px] h-[400px] rounded-full pointer-events-none"
        style={{
          background: 'radial-gradient(circle, rgba(30,52,112,0.25) 0%, transparent 70%)',
          filter: 'blur(60px)',
        }}
      />

      {/* pill badge */}
      <div
        className="mb-6 flex items-center gap-2 px-3 py-1 rounded-full border text-xs text-navy-300"
        style={{ borderColor: 'rgba(61,92,168,0.4)', background: 'rgba(61,92,168,0.08)' }}
      >
        <span className="w-1.5 h-1.5 rounded-full bg-navy-400 animate-pulse" />
        Automação inteligente de conteúdo
      </div>

      {/* headline */}
      <h1
        className="text-center font-bold leading-tight max-w-3xl"
        style={{
          fontSize: 'clamp(2.2rem, 5vw, 3.8rem)',
          background: 'linear-gradient(135deg, #e8edf5 30%, #7890c2)',
          WebkitBackgroundClip: 'text',
          WebkitTextFillColor: 'transparent',
        }}
      >
        Transforme conteúdo bruto em clips prontos para publicar
      </h1>

      <p className="mt-6 text-center text-navy-300 max-w-xl leading-relaxed" style={{ fontSize: '1.05rem' }}>
        Lorem ipsum dolor sit amet, consectetur adipiscing elit. Suspendisse varius enim in eros elementum tristique — de áudio a reels em segundos.
      </p>

      <div className="mt-10 flex flex-col sm:flex-row items-center gap-4">
        <a
          href="/login"
          className="flex items-center gap-2 px-6 py-3 rounded-xl font-medium text-sm text-white transition-all"
          style={{ background: 'linear-gradient(135deg, #3d5ca8, #2f4a8f)', boxShadow: '0 0 24px rgba(61,92,168,0.35)' }}
          onMouseEnter={e => (e.currentTarget.style.boxShadow = '0 0 36px rgba(61,92,168,0.55)')}
          onMouseLeave={e => (e.currentTarget.style.boxShadow = '0 0 24px rgba(61,92,168,0.35)')}
        >
          Começar agora <ArrowRight size={15} />
        </a>
        <button className="flex items-center gap-2 px-6 py-3 rounded-xl font-medium text-sm text-navy-200 border border-navy-700 hover:border-navy-500 hover:text-white transition-all">
          <Play size={14} />
          Ver demo
        </button>
      </div>

      {/* scroll hint */}
      <a href="#features" className="absolute bottom-10 animate-bounce text-navy-600 hover:text-navy-400 transition-colors">
        <ChevronDown size={22} />
      </a>
    </section>
  )
}

const FEATURES = [
  {
    icon: <Scissors size={20} />,
    title: 'Corte automático',
    body: 'Lorem ipsum dolor sit amet, consectetur adipiscing elit. Quisque vehicula lorem at metus dictum, id gravida odio accumsan.',
  },
  {
    icon: <Layers size={20} />,
    title: 'Gestão de assets',
    body: 'Pellentesque habitant morbi tristique senectus. Etiam porta sem malesuada magna mollis euismod facilisis.',
  },
  {
    icon: <Zap size={20} />,
    title: 'Processamento rápido',
    body: 'Donec sed odio dui. Cras mattis consectetur purus sit amet fermentum. Nullam quis risus eget urna mollis.',
  },
  {
    icon: <Globe size={20} />,
    title: 'Publicação multi-canal',
    body: 'Aenean lacinia bibendum nulla sed consectetur. Praesent commodo cursus magna vel scelerisque nisl.',
  },
]

function Features() {
  return (
    <section id="features" className="py-32 px-6">
      <div className="max-w-6xl mx-auto">
        <FadeIn className="text-center mb-20">
          <p className="text-xs uppercase tracking-widest text-navy-500 mb-3">Funcionalidades</p>
          <h2 className="text-3xl font-bold text-navy-50">Tudo que você precisa, nada que não precisa</h2>
          <p className="mt-4 text-navy-400 max-w-md mx-auto">
            Vestibulum id ligula porta felis euismod semper. Duis mollis, est non commodo luctus.
          </p>
        </FadeIn>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
          {FEATURES.map((f, i) => (
            <FadeIn key={f.title} delay={i * 80}>
              <div
                className="h-full p-6 rounded-2xl border group hover:border-navy-500 transition-all duration-300"
                style={{
                  background: 'rgba(13,17,23,0.6)',
                  borderColor: 'rgba(61,92,168,0.2)',
                  backdropFilter: 'blur(8px)',
                }}
                onMouseEnter={e => (e.currentTarget.style.background = 'rgba(30,52,112,0.15)')}
                onMouseLeave={e => (e.currentTarget.style.background = 'rgba(13,17,23,0.6)')}
              >
                <div className="w-10 h-10 rounded-xl flex items-center justify-center mb-4 text-navy-400 group-hover:text-navy-300 transition-colors"
                  style={{ background: 'rgba(61,92,168,0.12)' }}>
                  {f.icon}
                </div>
                <h3 className="font-semibold text-navy-100 mb-2">{f.title}</h3>
                <p className="text-sm text-navy-400 leading-relaxed">{f.body}</p>
              </div>
            </FadeIn>
          ))}
        </div>
      </div>
    </section>
  )
}

const STEPS = [
  { n: '01', title: 'Cole a URL', body: 'Lorem ipsum dolor sit amet, consectetur adipiscing elit. Integer nec odio.' },
  { n: '02', title: 'Configure os parâmetros', body: 'Praesent libero. Sed cursus ante dapibus diam. Sed nisi. Nulla quis sem.' },
  { n: '03', title: 'Revise os clips', body: 'Proin vel ante a dui semper commodo. Phasellus sit amet ultrices quam.' },
  { n: '04', title: 'Exporte e publique', body: 'Aliquam erat volutpat. Nam dui mi, tincidunt quis, accumsan porttitor.' },
]

function HowItWorks() {
  return (
    <section id="how" className="py-32 px-6" style={{ background: 'rgba(6,13,30,0.5)' }}>
      <div className="max-w-5xl mx-auto">
        <FadeIn className="text-center mb-20">
          <p className="text-xs uppercase tracking-widest text-navy-500 mb-3">Processo</p>
          <h2 className="text-3xl font-bold text-navy-50">Como funciona</h2>
        </FadeIn>

        <div className="relative">
          {/* connector line */}
          <div className="hidden lg:block absolute top-8 left-[calc(12.5%+1rem)] right-[calc(12.5%+1rem)] h-px"
            style={{ background: 'linear-gradient(90deg, transparent, rgba(61,92,168,0.4), rgba(61,92,168,0.4), transparent)' }} />

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-10">
            {STEPS.map((s, i) => (
              <FadeIn key={s.n} delay={i * 100} className="flex flex-col items-center text-center">
                <div
                  className="w-16 h-16 rounded-2xl flex items-center justify-center mb-5 font-bold text-lg relative z-10"
                  style={{
                    background: 'linear-gradient(135deg, rgba(61,92,168,0.3), rgba(30,52,112,0.5))',
                    border: '1px solid rgba(61,92,168,0.4)',
                    color: '#7890c2',
                  }}
                >
                  {s.n}
                </div>
                <h3 className="font-semibold text-navy-100 mb-2">{s.title}</h3>
                <p className="text-sm text-navy-400 leading-relaxed">{s.body}</p>
              </FadeIn>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}

const PLANS = [
  {
    name: 'Free',
    price: 'R$ 0',
    period: '/mês',
    highlight: false,
    features: ['5 clips por mês', 'Lorem ipsum feature', 'Suporte básico'],
  },
  {
    name: 'Pro',
    price: 'R$ 49',
    period: '/mês',
    highlight: true,
    features: ['Clips ilimitados', 'Lorem ipsum feature', 'Exportação multi-formato', 'Suporte prioritário'],
  },
  {
    name: 'Enterprise',
    price: 'Custom',
    period: '',
    highlight: false,
    features: ['Tudo do Pro', 'SLA garantido', 'API dedicada', 'Lorem ipsum feature'],
  },
]

function Pricing() {
  return (
    <section id="pricing" className="py-32 px-6">
      <div className="max-w-5xl mx-auto">
        <FadeIn className="text-center mb-20">
          <p className="text-xs uppercase tracking-widest text-navy-500 mb-3">Preços</p>
          <h2 className="text-3xl font-bold text-navy-50">Simples e transparente</h2>
          <p className="mt-4 text-navy-400 max-w-md mx-auto">
            Cras mattis consectetur purus sit amet fermentum. Integer posuere erat a ante.
          </p>
        </FadeIn>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 items-center">
          {PLANS.map((p, i) => (
            <FadeIn key={p.name} delay={i * 80}>
              <div
                className="p-8 rounded-2xl border transition-all duration-300"
                style={{
                  background: p.highlight ? 'linear-gradient(135deg, rgba(61,92,168,0.2), rgba(30,52,112,0.3))' : 'rgba(13,17,23,0.6)',
                  borderColor: p.highlight ? 'rgba(61,92,168,0.6)' : 'rgba(61,92,168,0.2)',
                  boxShadow: p.highlight ? '0 0 40px rgba(61,92,168,0.15)' : 'none',
                  transform: p.highlight ? 'scale(1.03)' : 'scale(1)',
                }}
              >
                {p.highlight && (
                  <div className="mb-4 inline-block px-3 py-0.5 rounded-full text-xs font-medium text-navy-200"
                    style={{ background: 'rgba(61,92,168,0.3)', border: '1px solid rgba(61,92,168,0.4)' }}>
                    Popular
                  </div>
                )}
                <p className="text-navy-400 text-sm mb-1">{p.name}</p>
                <div className="flex items-end gap-1 mb-6">
                  <span className="text-4xl font-bold text-white">{p.price}</span>
                  <span className="text-navy-400 mb-1">{p.period}</span>
                </div>
                <ul className="space-y-3 mb-8">
                  {p.features.map(f => (
                    <li key={f} className="flex items-center gap-2 text-sm text-navy-300">
                      <span className="w-1 h-1 rounded-full bg-navy-500 flex-shrink-0" />
                      {f}
                    </li>
                  ))}
                </ul>
                <button
                  className="w-full py-2.5 rounded-xl text-sm font-medium transition-all"
                  style={
                    p.highlight
                      ? { background: 'linear-gradient(135deg, #3d5ca8, #2f4a8f)', color: '#fff', boxShadow: '0 0 20px rgba(61,92,168,0.3)' }
                      : { background: 'transparent', color: '#9fb0d4', border: '1px solid rgba(61,92,168,0.3)' }
                  }
                >
                  {p.price === 'Custom' ? 'Falar com vendas' : 'Começar'}
                </button>
              </div>
            </FadeIn>
          ))}
        </div>
      </div>
    </section>
  )
}

function CTA() {
  return (
    <section className="py-32 px-6">
      <FadeIn>
        <div
          className="max-w-4xl mx-auto rounded-3xl p-16 text-center relative overflow-hidden"
          style={{
            background: 'linear-gradient(135deg, rgba(30,52,112,0.4), rgba(61,92,168,0.15))',
            border: '1px solid rgba(61,92,168,0.25)',
          }}
        >
          <div className="absolute inset-0 pointer-events-none"
            style={{ background: 'radial-gradient(circle at 50% 0%, rgba(61,92,168,0.2) 0%, transparent 70%)' }} />
          <h2 className="text-3xl font-bold text-white mb-4 relative">Pronto para automatizar seu conteúdo?</h2>
          <p className="text-navy-300 mb-10 max-w-md mx-auto relative">
            Aenean eu leo quam. Pellentesque ornare sem lacinia quam venenatis vestibulum.
          </p>
          <a
            href="/login"
            className="inline-flex items-center gap-2 px-8 py-3.5 rounded-xl font-medium text-sm text-white relative"
            style={{ background: 'linear-gradient(135deg, #3d5ca8, #2f4a8f)', boxShadow: '0 0 32px rgba(61,92,168,0.45)' }}
          >
            Criar conta grátis <ArrowRight size={15} />
          </a>
        </div>
      </FadeIn>
    </section>
  )
}

function Footer() {
  return (
    <footer className="border-t py-10 px-6" style={{ borderColor: 'rgba(61,92,168,0.15)' }}>
      <div className="max-w-6xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-md bg-gradient-to-br from-navy-500 to-navy-700 flex items-center justify-center">
            <Scissors size={12} className="text-white" />
          </div>
          <span className="text-sm font-medium text-navy-300">Anonimo</span>
        </div>
        <p className="text-xs text-navy-600">© {new Date().getFullYear()} Anonimo. Todos os direitos reservados.</p>
        <nav className="flex gap-6 text-xs text-navy-600">
          <a href="#" className="hover:text-navy-400 transition-colors">Privacidade</a>
          <a href="#" className="hover:text-navy-400 transition-colors">Termos</a>
        </nav>
      </div>
    </footer>
  )
}

// ---------- page ----------

export default function LandingPage() {
  return (
    <div className="min-h-screen" style={{ background: '#0a1530', color: '#e8edf5' }}>
      <Navbar />
      <Hero />
      <Features />
      <HowItWorks />
      <Pricing />
      <CTA />
      <Footer />
    </div>
  )
}
