/**
 * Animated ocean backdrop, as a MapLibre CustomLayerInterface.
 *
 * The map's "sea" was a single flat background-color paint property — this
 * replaces that with a fullscreen fragment shader (layered scrolling noise,
 * a soft caustic shimmer, a fresnel-style brightening toward the horizon)
 * rendered directly into MapLibre's own WebGL context and render loop.
 *
 * Deliberately NOT georeferenced: it draws a fixed fullscreen quad in clip
 * space rather than using the camera projection matrix MapLibre passes to
 * render(). This is a stylistic backdrop standing in for "open water", not
 * real bathymetry tied to lon/lat, so it never needs to move, scale or
 * rotate with the camera -- which also means it costs nothing extra when
 * panning/zooming (no geometry to re-project, just a full-viewport pass).
 *
 * Added as the very first layer (before "bg") so every existing vector/
 * raster layer keeps drawing on top of it exactly as before.
 */

import type { CustomLayerInterface, Map as MLMap } from "maplibre-gl";

const VERT_SRC = `
attribute vec2 a_pos;
varying vec2 v_uv;
void main() {
  v_uv = a_pos * 0.5 + 0.5;
  gl_Position = vec4(a_pos, 0.0, 1.0);
}
`;

// Cheap value-noise + fbm, entirely self-contained (no texture lookups) so
// this stays a single small shader with no asset loading.
const FRAG_SRC = `
precision mediump float;
varying vec2 v_uv;

uniform float u_time;
uniform vec2 u_resolution;
uniform vec3 u_deep;
uniform vec3 u_shallow;
uniform vec3 u_highlight;

float hash(vec2 p) {
  p = fract(p * vec2(123.34, 456.21));
  p += dot(p, p + 45.32);
  return fract(p.x * p.y);
}

float noise(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  float a = hash(i);
  float b = hash(i + vec2(1.0, 0.0));
  float c = hash(i + vec2(0.0, 1.0));
  float d = hash(i + vec2(1.0, 1.0));
  vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(a, b, u.x) + (c - a) * u.y * (1.0 - u.x) + (d - b) * u.x * u.y;
}

float fbm(vec2 p) {
  float v = 0.0;
  float amp = 0.5;
  for (int i = 0; i < 4; i++) {
    v += amp * noise(p);
    p *= 2.02;
    amp *= 0.55;
  }
  return v;
}

void main() {
  vec2 uv = v_uv;
  float aspect = u_resolution.x / max(u_resolution.y, 1.0);
  vec2 p = vec2(uv.x * aspect, uv.y);

  // Two slow-drifting noise fields at different scales/speeds — the same
  // "layered motion at different rates" trick that reads as depth in a
  // 2D fluid surface, rather than one field that looks like scrolling static.
  float t = u_time * 0.035;
  float swell = fbm(p * 2.2 + vec2(t * 0.6, t * 0.25));
  float ripple = fbm(p * 6.0 - vec2(t * 1.1, t * 0.4));
  float waves = swell * 0.7 + ripple * 0.3;

  // Depth gradient: darker/deeper toward the top of the viewport, lighter
  // toward the bottom, independent of the wave field -- gives the flat
  // fill actual tonal structure instead of one uniform hex value.
  float depth = smoothstep(0.0, 1.0, 1.0 - uv.y);
  vec3 base = mix(u_deep, u_shallow, depth);

  // Wave field modulates brightness, not color -- keeps hue consistent so
  // it still reads as "water", not a noise texture.
  vec3 color = base + waves * 0.05;

  // A soft moving specular band standing in for sun/sky glint, low-frequency
  // so it drifts rather than sparkles per-pixel.
  float glint = pow(max(0.0, fbm(p * 1.4 + vec2(t * 0.3, -t * 0.15))), 3.0);
  color += u_highlight * glint * 0.18;

  gl_FragColor = vec4(color, 1.0);
}
`;

function compileShader(gl: WebGLRenderingContext, type: number, src: string): WebGLShader {
  const shader = gl.createShader(type)!;
  gl.shaderSource(shader, src);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    const info = gl.getShaderInfoLog(shader);
    gl.deleteShader(shader);
    throw new Error(`ocean shader compile failed: ${info}`);
  }
  return shader;
}

/** [r, g, b] in 0-1, from a "#rrggbb" string. */
function hexToRgb(hex: string): [number, number, number] {
  const n = parseInt(hex.replace("#", ""), 16);
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
}

export interface OceanPalette {
  deep: string;
  shallow: string;
  highlight: string;
}

export const OCEAN_PALETTES: Record<"light" | "dark", OceanPalette> = {
  // Matches the existing light/dark bg colors (#e0f2fe / #06132b) as the
  // shallow/deep ends of the gradient, so this reads as a richer version of
  // the same sea tone rather than a mismatched new color.
  light: { deep: "#bfe3fb", shallow: "#eef9ff", highlight: "#ffffff" },
  dark: { deep: "#040d1f", shallow: "#0a2547", highlight: "#5eead4" },
};

export class OceanLayer implements CustomLayerInterface {
  id = "ocean-backdrop";
  type = "custom" as const;
  renderingMode = "2d" as const;

  private program: WebGLProgram | null = null;
  private buffer: WebGLBuffer | null = null;
  private aPos = -1;
  private uTime: WebGLUniformLocation | null = null;
  private uResolution: WebGLUniformLocation | null = null;
  private uDeep: WebGLUniformLocation | null = null;
  private uShallow: WebGLUniformLocation | null = null;
  private uHighlight: WebGLUniformLocation | null = null;

  private palette: OceanPalette = OCEAN_PALETTES.light;
  private startTime = performance.now();

  setPalette(palette: OceanPalette) {
    this.palette = palette;
  }

  onAdd(_map: MLMap, gl: WebGLRenderingContext) {
    const vert = compileShader(gl, gl.VERTEX_SHADER, VERT_SRC);
    const frag = compileShader(gl, gl.FRAGMENT_SHADER, FRAG_SRC);
    const program = gl.createProgram()!;
    gl.attachShader(program, vert);
    gl.attachShader(program, frag);
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      throw new Error(`ocean shader link failed: ${gl.getProgramInfoLog(program)}`);
    }
    this.program = program;
    this.aPos = gl.getAttribLocation(program, "a_pos");
    this.uTime = gl.getUniformLocation(program, "u_time");
    this.uResolution = gl.getUniformLocation(program, "u_resolution");
    this.uDeep = gl.getUniformLocation(program, "u_deep");
    this.uShallow = gl.getUniformLocation(program, "u_shallow");
    this.uHighlight = gl.getUniformLocation(program, "u_highlight");

    // A single fullscreen triangle-strip quad in clip space; never touched
    // again after upload, since it isn't tied to any geographic coordinate.
    this.buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this.buffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
  }

  render(gl: WebGLRenderingContext) {
    if (!this.program || !this.buffer) return;
    gl.useProgram(this.program);

    gl.bindBuffer(gl.ARRAY_BUFFER, this.buffer);
    gl.enableVertexAttribArray(this.aPos);
    gl.vertexAttribPointer(this.aPos, 2, gl.FLOAT, false, 0, 0);

    const elapsedSeconds = (performance.now() - this.startTime) / 1000;
    gl.uniform1f(this.uTime, elapsedSeconds);
    gl.uniform2f(this.uResolution, gl.drawingBufferWidth, gl.drawingBufferHeight);

    const [dr, dg, db] = hexToRgb(this.palette.deep);
    const [sr, sg, sb] = hexToRgb(this.palette.shallow);
    const [hr, hg, hb] = hexToRgb(this.palette.highlight);
    gl.uniform3f(this.uDeep, dr, dg, db);
    gl.uniform3f(this.uShallow, sr, sg, sb);
    gl.uniform3f(this.uHighlight, hr, hg, hb);

    // No depth test / no blending: this is the very back of the scene, drawn
    // once per frame before MapLibre's own layers composite on top.
    gl.disable(gl.DEPTH_TEST);
    gl.disable(gl.BLEND);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
  }

  onRemove(_map: MLMap, gl: WebGLRenderingContext) {
    if (this.program) gl.deleteProgram(this.program);
    if (this.buffer) gl.deleteBuffer(this.buffer);
    this.program = null;
    this.buffer = null;
  }
}
