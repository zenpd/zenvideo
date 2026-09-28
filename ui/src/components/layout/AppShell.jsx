import { Sidebar } from './Sidebar'
import { Header } from '../Header'
import { Footer } from './Footer'

/**
 * Dashboard shell: fixed sidebar + fixed header + scrollable content + footer.
 * Mirrors the ZenLabs AppShell/Sidebar/Header pattern.
 */
export function AppShell({ title, subtitle, search, onSearchChange, online, children }) {
  return (
    <div className="min-h-screen bg-gray-50">
      <Sidebar online={online} />
      <Header
        title={title}
        subtitle={subtitle}
        search={search}
        onSearchChange={onSearchChange}
        online={online}
      />

      <main className="ml-[240px] mt-[60px] mb-[44px] min-h-[calc(100vh-104px)] overflow-y-auto">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-6 animate-fade-in">
          {children}
        </div>
      </main>

      <Footer />
    </div>
  )
}
