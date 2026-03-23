import './globals.css'

export const metadata = {
  title: 'AI Customer Support',
  description: 'Intelligent intent-based customer support chatbot',
}

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <div className="bg-animated"></div>
        {children}
      </body>
    </html>
  )
}
