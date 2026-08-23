/** Layer colours, shared between the map and the legend so they can never
 *  drift apart. */
export const C = {
  slick: "#f0a03c",
  slickFill: "rgba(240, 160, 60, 0.28)",
  reject: "#93a6c2",
  rejectFill: "rgba(107, 122, 146, 0.12)",
  cone90: "rgba(53, 200, 216, 0.10)",
  cone50: "rgba(53, 200, 216, 0.22)",
  coneLine: "#35c8d8",
  particle: "#8be9f0",
  origin: "#35c8d8",
  vessel: "#7ee0a8",
  vesselDim: "rgba(126, 224, 168, 0.18)",
  suspect: "#f2545b",
  forecast: "#c98bf0",
} as const;
