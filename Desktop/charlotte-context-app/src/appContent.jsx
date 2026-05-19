import { useContext } from "react";
import { ThemeContext } from "./Context/ThemeContext";
import Buttons from "./Components/Buttons";

function appContent() {
  const { themeColour } = useContext(ThemeContext);

  console.log("AppContent theme:", themeColour); // 👈 DEBUG

  return (
    <div className={`app ${themeColour}`}>
      <h1>Test theme</h1>
      <Buttons />
    </div>
  );
}

export default appContent;
