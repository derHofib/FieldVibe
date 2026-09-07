import { Moon, Sun } from "lucide-react";

import { useTheme } from "../context/ThemeContext";

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();

  return (
    <button
      onClick={toggleTheme}
      title={theme === "dark" ? "Helles Design" : "Dunkles Design"}
      className="btn-touch btn-industry btn-industry-secondary btn-industry-icon"
    >
      {theme === "dark" ? <Sun size={17} strokeWidth={1.5} /> : <Moon size={17} strokeWidth={1.5} />}
    </button>
  );
}
