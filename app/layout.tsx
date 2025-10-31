import type { Metadata } from 'next'
import Link from 'next/link'
import './globals.css'
import { SocketProvider } from '../lib/socket/socket-context'

export const metadata: Metadata = {
  title: 'LangGraph Agent Chat',
  description: 'AI-powered code generation with LangGraph and OpenRouter',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body>
        <SocketProvider>
          <nav className="bg-white border-b border-gray-200 px-4 py-3">
            <div className="max-w-7xl mx-auto flex items-center justify-between">
              <div className="flex items-center space-x-8">
                <Link href="/" className="text-xl font-bold text-gray-900">
                  LangGraph Agent
                </Link>
                <div className="flex items-center space-x-4">
                  <Link
                    href="/"
                    className="text-gray-600 hover:text-gray-900 px-3 py-2 rounded-md text-sm font-medium"
                  >
                    AI Chat
                  </Link>
                  <Link
                    href="/sandbox"
                    className="text-gray-600 hover:text-gray-900 px-3 py-2 rounded-md text-sm font-medium"
                  >
                    Sandbox Manager
                  </Link>
                </div>
              </div>
            </div>
          </nav>
          {children}
        </SocketProvider>
      </body>
    </html>
  )
}
