"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";

export type ThemeChoice = "dark" | "light" | "system";

const KEY = "receiptauto:theme";

/* Runs before first paint, inlined in <head>. Without it the dark default
   paints, then the stored choice applies, and a light-mode user gets a black
   flash on every navigation. */
export const THEME_SCRIPT = `(function(){try{
var c=localStorage.getItem(${JSON.stringify(KEY)})||"system";
var m=window.matchMedia("(prefers-color-scheme: light)").matches;
document.documentElement.dataset.theme=c==="system"?(m?"light":"dark"):c;
}catch(e){document.documentElement.dataset.theme="dark";}})();`;

function resolve(choice: ThemeChoice): "dark" | "light" {
  if (choice !== "system") return choice;
  if (typeof window === "undefined") return "dark";
  return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

const Ctx = createContext<{ choice: ThemeChoice; setChoice: (c: ThemeChoice) => void }>({
  choice: "system",
  setChoice: () => {},
});

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [choice, setState] = useState<ThemeChoice>("system");

  useEffect(() => {
    setState((localStorage.getItem(KEY) as ThemeChoice) || "system");
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = resolve(choice);
    if (choice !== "system") return;
    // Following the OS means following it *while* the app is open, not only at
    // load. Someone on an automatic day/night schedule should not have to
    // reload at dusk.
    const query = window.matchMedia("(prefers-color-scheme: light)");
    const sync = () => {
      document.documentElement.dataset.theme = query.matches ? "light" : "dark";
    };
    query.addEventListener("change", sync);
    return () => query.removeEventListener("change", sync);
  }, [choice]);

  const setChoice = useCallback((next: ThemeChoice) => {
    setState(next);
    localStorage.setItem(KEY, next);
  }, []);

  return <Ctx.Provider value={{ choice, setChoice }}>{children}</Ctx.Provider>;
}

export const useTheme = () => useContext(Ctx);
