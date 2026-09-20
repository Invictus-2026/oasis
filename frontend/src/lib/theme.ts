/** Layer colours, shared between the map and the legend so they can never
 *  drift apart. */
export const C = {
  slick: "#c97c2c",
  slickFill: "rgba(201, 124, 44, 0.28)",
  reject: "#7d979d",
  rejectFill: "rgba(107, 130, 136, 0.12)",
  cone90: "rgba(8, 145, 178, 0.10)",
  cone50: "rgba(8, 145, 178, 0.22)",
  coneLine: "#0891b2",
  particle: "#0891b2",
  origin: "#0891b2",
  vessel: "#22b869",
  vesselDim: "rgba(34, 184, 105, 0.18)",
  suspect: "#ff5a1f",
  forecast: "#4c5fd5",
  /** Ambient shipping lanes — background texture, so it stays well below the
   *  data layers in contrast. Deliberately a mid sea-tone: the lanes cross
   *  both the pale ocean fill and the dark SAR raster, and a darker tone
   *  disappears entirely over the imagery. */
  lane: "#8fa3a8",
  laneDark: "#3d6a72",
} as const;
