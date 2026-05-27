import { useState } from 'react'
import { Menu } from 'lucide-react'
import Sidebar from './Sidebar'

interface LayoutProps {
  children: React.ReactNode
  title?: string
  description?: string
}

export default function Layout({ children, title, description }: LayoutProps) {
  const [sidebarOpen, setSidebarOpen] = useState(false)

  return (
    <div className="flex min-h-screen" style={{ background: '#0d1117' }}>
      {/* Overlay mobile */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-20 bg-black/60 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar desktop */}
      <div className="hidden lg:flex">
        <Sidebar />
      </div>

      {/* Sidebar mobile (drawer) */}
      <div className={`fixed inset-y-0 left-0 z-30 lg:hidden transition-transform duration-300 ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}`}>
        <Sidebar onClose={() => setSidebarOpen(false)} />
      </div>

      <div className="flex-1 flex flex-col min-w-0">
        {/* Topbar */}
        <header className="h-16 flex items-center gap-4 px-4 lg:px-8 border-b border-navy-900 sticky top-0 z-10" style={{ background: '#141920' }}>
          <button
            className="lg:hidden text-navy-400 hover:text-white transition-colors"
            onClick={() => setSidebarOpen(true)}
          >
            <Menu size={20} />
          </button>
          {title && (
            <div>
              <h1 className="text-sm font-semibold text-white leading-tight">{title}</h1>
              {description && <p className="text-xs text-navy-400 hidden sm:block">{description}</p>}
            </div>
          )}
        </header>

        <main className="flex-1 p-4 lg:p-8 overflow-auto">
          {children}
        </main>
      </div>
    </div>
  )
}
