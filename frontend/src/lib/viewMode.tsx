import { createContext, useContext, type ReactNode } from "react";

export type ViewMode = "analyst" | "executive";

const ViewModeContext = createContext<ViewMode>("analyst");

export const ViewModeProvider = ViewModeContext.Provider;

export function useViewMode(): ViewMode {
  return useContext(ViewModeContext);
}

/** Wraps content that only belongs in front of a technical audience — raw
 *  sub-scores, method notes, intermediate candidates, timestamps. Honesty
 *  caveats (disclaimers, limitations, fixture labelling) are never wrapped in
 *  this: those stay visible in both modes on principle. */
export function AnalystOnly({ children }: { children: ReactNode }) {
  return useViewMode() === "analyst" ? <>{children}</> : null;
}
