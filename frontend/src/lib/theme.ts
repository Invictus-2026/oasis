import { useCallback, useEffect, useState } from "react";

export type ThemeMode = "light" | "dark";

const STORAGE_KEY = "theme";

function systemPrefersDark(): boolean {
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function applyTheme(mode: ThemeMode) {
  document.documentElement.classList.toggle("dark", mode === "dark");
}

/** Tracks light/dark theme, mirrors it onto the <html class="dark"> switch
 *  index.css keys off of, and persists explicit user choices. Until the
 *  user toggles manually, it follows the OS scheme so the app matches the
 *  index.html init script's first-paint decision and stays in sync if the
 *  OS theme changes underneath it. */
export function useTheme() {
  const [theme, setTheme] = useState<ThemeMode>(() =>
    document.documentElement.classList.contains("dark") ? "dark" : "light",
  );

  useEffect(() => {
    if (localStorage.getItem(STORAGE_KEY)) return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => {
      const mode = systemPrefersDark() ? "dark" : "light";
      applyTheme(mode);
      setTheme(mode);
    };
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme((prev) => {
      const next: ThemeMode = prev === "dark" ? "light" : "dark";
      applyTheme(next);
      localStorage.setItem(STORAGE_KEY, next);
      return next;
    });
  }, []);

  return { theme, toggleTheme };
}

/** Layer colours, shared between the map and the legend so they can never
 *  drift apart. */
export const C = {
  slick: "#f0a03c",
  slickFill: "rgba(240, 160, 60, 0.28)",
  reject: "#93a6c2",
  rejectFill: "rgba(107, 122, 146, 0.12)",
  cone90: "rgba(37, 99, 235, 0.10)",
  cone50: "rgba(37, 99, 235, 0.22)",
  coneLine: "#2563eb",
  particle: "#2563eb",
  origin: "#2563eb",
  vessel: "#10b981",
  vesselDim: "rgba(16, 185, 129, 0.18)",
  suspect: "#ef4444",
  forecast: "#9333ea",
} as const;
