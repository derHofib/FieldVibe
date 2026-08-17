import { Moon, Sun } from "lucide-react";

import { useTheme } from "../context/ThemeContext";

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();

  return (
    <button
      onClick={toggleTheme}
      title={theme === "dark" ? "Helles Design" : "Dunkles Design"}
      className="btn-touch flex items-center justify-center rounded-md px-2 text-slate-500 hover:bg-slate-100 dark:text-stone-400 dark:hover:bg-stone-800"
    >
      {theme === "dark" ? <Sun size={17} strokeWidth={2} /> : <Moon size={17} strokeWidth={2} />}
    </button>
  );
}
