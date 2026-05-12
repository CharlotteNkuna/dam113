import { createContext, useState } from "react";
//create context
export const ThemeContext = createContext();
//create provider
export const ThemeProvider = ({ children }) => {
  const [themeColour, setThemeColour] = useState("light");

  return (
    <ThemeContext.Provider value={{ themeColour, setThemeColour }}>
      {children}
    </ThemeContext.Provider>
  );
};
