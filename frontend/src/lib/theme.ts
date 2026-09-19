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
  /** Ambient shipping lanes — background texture, so it stays well below the
   *  data layers in contrast. Deliberately a mid slate: the lanes cross both
   *  the pale ocean fill and the dark SAR raster, and a darker tone
   *  disappears entirely over the imagery. */
  lane: "#94a3b8",
  laneDark: "#758398",
} as const;
