"use client";

import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";

export function ThemeToggle() {
  const [mounted, setMounted] = useState(false);
  const { resolvedTheme, setTheme } = useTheme();

  useEffect(() => {
    setMounted(true);
  }, []);

  const theme = mounted ? resolvedTheme ?? "light" : "light";
  const isDark = theme === "dark";

  return (
    <button
      className="theme-toggle"
      type="button"
      aria-label="Toggle theme"
      onClick={() => setTheme(isDark ? "light" : "dark")}
    >
      <span className="theme-toggle__icon-wrap" aria-hidden="true">
        <Sun className={`theme-toggle__icon theme-toggle__icon--sun ${isDark ? "is-hidden" : ""}`} />
        <Moon className={`theme-toggle__icon theme-toggle__icon--moon ${isDark ? "" : "is-hidden"}`} />
      </span>
      <span className="theme-toggle__text">
        <span className="theme-toggle__title">Theme</span>
        <span className="theme-toggle__value">{isDark ? "Dark" : "Light"}</span>
      </span>
    </button>
  );
}
