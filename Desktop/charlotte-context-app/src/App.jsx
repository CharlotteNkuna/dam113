import { ThemeProvider } from './Context/ThemeContext'
import AppContent from './appContent'
import './App.css'

function App() {
  return (
    <ThemeProvider>
      <AppContent />
    </ThemeProvider>
  )
}

export default App
