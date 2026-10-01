import { useSyncExternalStore } from "react";

const THEME_KEY = "bm-theme";
const THEME_EVENT = "bm-theme";

export type Theme = "dark" | "light";

export function getTheme(): Theme {
  return document.documentElement.dataset.theme === "light" ? "light" : "dark";
}

export function setTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.background = theme === "light" ? "#f3f4f6" : "#050506";
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", theme === "light" ? "#f3f4f6" : "#050506");
  try {
    localStorage.setItem(THEME_KEY, theme);
  } catch {
    // Private mode: the choice lasts for this visit only.
  }
  window.dispatchEvent(new Event(THEME_EVENT));
}

export function toggleTheme() {
  setTheme(getTheme() === "light" ? "dark" : "light");
}

export function useTheme(): Theme {
  return useSyncExternalStore(
    (onChange) => {
      window.addEventListener(THEME_EVENT, onChange);
      return () => window.removeEventListener(THEME_EVENT, onChange);
    },
    getTheme,
    () => "dark",
  );
}
