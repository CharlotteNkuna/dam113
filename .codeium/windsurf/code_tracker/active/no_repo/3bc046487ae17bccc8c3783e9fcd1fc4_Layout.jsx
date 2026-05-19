¡import Header from './Header'
import Footer from './Footer'
import { Outlet } from 'react-router-dom'

export default function Layout() {
  return (
    <div className="app">
      <Header />
      <main className="main">
        <Outlet />
      </main>
      <Footer />
    </div>
  )
}
µ *cascade08µÄÄ¡ *cascade082@file:///Users/dam113/Desktop/liquorose/src/components/Layout.jsx