import { useState } from 'react'

interface Tab {
  label: string
  content: React.ReactNode
}

export default function Tabs({ tabs }: { tabs: Tab[] }) {
  const [active, setActive] = useState(0)

  return (
    <div>
      <div className="flex border-b border-navy-800 mb-6">
        {tabs.map((tab, i) => (
          <button
            key={i}
            type="button"
            onClick={() => setActive(i)}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px ${
              active === i
                ? 'border-navy-400 text-white'
                : 'border-transparent text-navy-400 hover:text-navy-200'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div>{tabs[active].content}</div>
    </div>
  )
}
