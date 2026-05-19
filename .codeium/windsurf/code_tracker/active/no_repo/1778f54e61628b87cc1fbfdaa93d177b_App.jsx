ãimport './App.css'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Home from './pages/Home'
import About from './pages/About'
import Store from './pages/Store'
import Own from './pages/Own'
import Contact from './pages/Contact'
import Layout from './components/Layout'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Home />} />
          <Route path="about" element={<About />} />
          <Route path="store" element={<Store />} />
          <Route path="own" element={<Own />} />
          <Route path="contact" element={<Contact />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
 *cascade08ZZi *cascade08ij*cascade08jm *cascade08mn*cascade08ns *cascade08sû*cascade08û¤*cascade08¤¿ *cascade08¿…*cascade08…† *cascade08†³³´ *cascade08´µ*cascade08µº *cascade08º¿ *cascade08¿Á*cascade08Áô *cascade08ôö*cascade08ö© *cascade08©ª*cascade08ª² *cascade08²³*cascade08³Ú *cascade08ÚÜ*cascade08Ü‘ *cascade08‘¢¢Ì *cascade08Ìã *cascade0822file:///Users/dam113/Desktop/liquorose/src/App.jsx