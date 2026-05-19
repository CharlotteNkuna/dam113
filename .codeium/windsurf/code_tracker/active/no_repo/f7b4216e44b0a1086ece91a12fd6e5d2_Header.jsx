›	import { Link } from 'react-router-dom'
import { useState } from 'react'

export default function Header() {
  const [open, setOpen] = useState(false)
  return (
    <header className="header">
      <div className="header-top">
        <h1>Liquorose</h1>
        <button
          className="menu-toggle"
          aria-label="Toggle navigation"
          aria-expanded={open ? 'true' : 'false'}
          onClick={() => setOpen(!open)}
        >
          <svg width="22" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
            <path d="M4 6h16M4 12h16M4 18h16" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
          </svg>
        </button>
        <nav className={`nav ${open ? 'open' : ''}`}>
          <ul>
            <li><Link to="/">Home</Link></li>
            <li><Link to="/about">About</Link></li>
            <li><Link to="/store">Store</Link></li>
            <li><Link to="/own">Own a Liquorose</Link></li>
            <li><Link to="/contact">Contact</Link></li>
          </ul>
        </nav>
      </div>
      <p className="subtitle">Find cocktails from Liquorose</p>
    </header>
  )
}
( *cascade08(I*cascade08IJ *cascade08Jm *cascade08m—*cascade08—É *cascade08É€ *cascade08€Ì *cascade08Ì*cascade08‘ *cascade08‘©*cascade08©ª *cascade08ª³*cascade08³´ *cascade08´»*cascade08»½ *cascade08½¿*cascade08¿Ì *cascade08Ìø*cascade08øù *cascade08ù€*cascade08€ *cascade08¦*cascade08¦µ *cascade08µ¸*cascade08¸Ì *cascade08ÌÕ *cascade08Õã *cascade08ãå*cascade08åè *cascade08è€*cascade08€Š *cascade08ŠŒ*cascade08Œ‘ *cascade08‘“*cascade08“¢ *cascade08¢¦*cascade08¦§ *cascade08§©*cascade08©« *cascade08«¬*cascade08¬´ *cascade08´¸*cascade08¸É *cascade08ÉË*cascade08ËĞ *cascade08ĞÔ*cascade08ÔÕ *cascade08Õ×*cascade08×Ù *cascade08ÙÚ*cascade08Úè *cascade08èì*cascade08ìó *cascade08óõ*cascade08õ„ *cascade08„ˆ*cascade08ˆ‰ *cascade08‰‹*cascade08‹ *cascade08*cascade08œ *cascade08œ *cascade08 § *cascade08§©*cascade08©¸ *cascade08¸¼*cascade08¼½ *cascade08½¿*cascade08¿Á *cascade08ÁÂ*cascade08ÂØ *cascade08ØÜ*cascade08Üí *cascade08íï*cascade08ïô *cascade08ôø*cascade08øù *cascade08ùû*cascade08ûı *cascade08ış*cascade08ş *cascade08”*cascade08”£ *cascade08£¥*cascade08¥« *cascade08«­*cascade08­¸ *cascade08¸º *cascade08ºº*cascade08ºÂ *cascade08ÂÅ*cascade08ÅÆ *cascade08
ÆÍ Íù *cascade08
ùü 2ü‚	*$d12b0bc4-cc42-478e-85b5-b72561511fdc08‚	…	 *cascade08…	‹	 *cascade08‹	›	 *cascade082@file:///Users/dam113/Desktop/liquorose/src/components/Header.jsx