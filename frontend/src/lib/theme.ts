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
