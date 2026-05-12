import { useContext } from "react"
import { ThemeContext } from "../Context/ThemeContext"

function Button() {
  const { themeColour, setThemeColour } = useContext(ThemeContext)
  console.log("Current theme:", themeColour); 


  const toggleTheme = () => {
    if (themeColour === "light") {
      setThemeColour("dark")
    } else {
      setThemeColour("light")
    }
  }

  return (
    <button onClick={toggleTheme}>
      Current theme: {themeColour}
    </button>
  )
}

export default Button
