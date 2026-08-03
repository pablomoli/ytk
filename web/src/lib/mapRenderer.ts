import type { MapData, MapFog, MapPoint, MapTerrain, MapWeb } from "../api/map";
import {
  DIM,
  focusLevel,
  groupTargets,
  pointDomain,
  pointGroup,
  pointPhases,
  ramp as ease,
} from "./mapGroups";
import type { MapFocus } from "./mapGroups";
import { decay, pushSample, releaseVelocity } from "./mapInertia";
import type { VelocitySample } from "./mapInertia";

export type MapHover = { point: MapPoint; x: number; y: number };
// A road waypoint by data.points index; positions resolve per frame in
// placeRoad() so the overlay tracks morph/dim/relief exactly like labels.
export type RoadWaypointRef = { index: number; kind: "a" | "stop" | "b"; title: string };
export type MapRenderer = {
  setView: (view: "all" | "content") => void;
  setDimension: (flat: boolean) => void;
  setFilters: (signal: boolean, recent: boolean, media?: boolean) => void;
  // Time machine position as a quantile of the dated corpus, 0..1. 1 shows
  // everything.
  setClock: (next: number) => void;
  setFocus: (focus: MapFocus) => void;
  setHover: (hover?: MapFocus) => void;
  setHiddenDomains: (doms: Set<number>) => void;
  setLegendOpen: (open: boolean) => void;
  setTerrain: (on: boolean) => void;
  setWeb: (on: boolean) => void;
  setFog: (on: boolean) => void;
  setFogLevel: (level: number) => void;
  setFogShell: (on: boolean) => void;
  // Road mode: while a pick callback is set, point clicks report to it and
  // the drill-down focus behavior is suspended.
  setRoadPick: (cb?: (point: MapPoint) => void) => void;
  setRoute: (route?: RoadWaypointRef[]) => void;
  flyTo: (point: MapPoint) => void;
  destroy: () => void;
};

// Both layouts ride in the buffer: p0/p1 are the 3D everything/content
// positions, q0/q1 the dedicated 2D embeddings. The morph uniform blends
// everything<->content, the dim uniform blends flat<->volume. Focus and
// hover dimming live in per-group uniform arrays (focDom/focSub A->B pairs)
// swept by a growth ramp phased from cluster centers, so focus changes are
// pure uniform animation over a static buffer too.
const vertex = `attribute vec3 p0; attribute vec3 p1; attribute vec2 q0; attribute vec2 q1;
attribute vec3 color0; attribute vec3 color1; attribute vec3 colorSub;
attribute float alpha0; attribute float alpha1; attribute float size;
attribute float grp; attribute float dm; attribute float phase;
attribute float hgt0; attribute float hgt1;
uniform float morph; uniform float dim; uniform float zoom; uniform vec2 pan;
uniform float theta; uniform float phi; uniform float dpr;
uniform float relief; uniform float hscale;
uniform float focDomA[32]; uniform float focDomB[32];
uniform float focSubA[96]; uniform float focSubB[96];
uniform float focusT; uniform float level; uniform float subColorT;
uniform float introT; uniform float time; uniform float clock;
// id and birth share one attribute because the point program sits exactly on
// WebGL1's 16-attribute ceiling — a 17th fails to COMPILE with "Too many
// attributes", at runtime, where no amount of typechecking can see it.
// .x is the pick id; .y is the note's date as a QUANTILE in 0..1, not a
// timestamp: the dates pile up so hard that half the corpus lands in the last
// 4% of the real span (docs/assets/07-time-machine/01-date-distribution.png).
// A negative .y means undated — whole categories rather than a random few, so
// they are exempted instead of being handed a birthday they never had.
attribute vec2 idBirth; uniform mediump float pickMode; uniform float pickPad;
varying vec3 c; varying float a; varying float depthV; varying vec3 pickC;
float rampf(float p){ return .5 - .5*cos(clamp(p,0.,1.)*3.14159265); }
void main(){
  vec3 p3=mix(p0,p1,morph); vec2 p2=mix(q0,q1,morph); vec3 q=mix(vec3(p2,0.),p3,dim);
  q.z+=mix(hgt0,hgt1,morph)*hscale*relief;
  float ct=cos(theta),st=sin(theta),cp=cos(phi),sp=sin(phi);
  q=vec3(ct*q.x+st*q.z,sp*(st*q.x-ct*q.z)+cp*q.y,-cp*(st*q.x-ct*q.z)+sp*q.y);
  float depth=1.35-q.z*.24; depthV=q.z;
  gl_Position=vec4(q.xy*.88*zoom/depth+pan,q.z*.12,1.);
  int di=int(dm+.5); int si=int(max(grp,0.)+.5);
  float r=rampf(focusT*1.6-phase*.6);
  float fa=grp<0. ? mix(focDomA[di],focDomB[di],r) : mix(focSubA[si],focSubB[si],r);
  // Same sweep the intro runs, driven by a date instead of a fixed timer.
  // The 24. sets the softness of the wavefront: a note takes about 1/24 of
  // the corpus to fade fully in, so the edge reads as a tide rather than a
  // switch. Undated notes (birth<0) are always present.
  float birth=idBirth.y;
  float born=birth<0. ? 1. : rampf((clock-birth)*24.);
  float grow=rampf(introT*1.8-phase*.8)*born;
  gl_PointSize=clamp(size*zoom/depth*dpr,1.8,26.*dpr)*grow+pickPad*pickMode;
  c=mix(mix(color0,colorSub,subColorT),color1,morph);
  float pulse=1.+.12*sin(time*2.2-phase*5.)*step(1.5,level+focusT);
  a=mix(alpha0,alpha1,morph)*fa*grow*pulse;
  // Encode the id here, not in the fragment shader. A float varying carrying
  // 4,067 would arrive as mediump downstream, which is only exact to ~1024,
  // so the id would quietly corrupt. Three bytes already scaled to 0..1
  // survive mediump with room to spare.
  float id=idBirth.x;
  pickC=vec3(mod(id,256.),mod(floor(id/256.),256.),mod(floor(id/65536.),256.))/255.; }`;
const fragment = `precision mediump float; varying vec3 c; varying float a; varying float depthV;
uniform mediump float pickMode; varying vec3 pickC;
void main(){ vec2 p=gl_PointCoord*2.-1.; float d2=dot(p,p); float edge=smoothstep(1.,.82,sqrt(d2)); if(edge<=0.) discard;
 if(pickMode>.5){
  // Colour is an integer wearing a costume: the 1-based id (0 = background)
  // already split into three bytes by the vertex shader. No blending, no AA
  // on this pass — a filtered edge pixel would decode to an unrelated id.
  if(a<.06) discard;  // invisible to the eye must be invisible to the cursor
  gl_FragColor=vec4(pickC,1.);
  return; }
 float z=sqrt(max(0.,1.-d2)); vec3 n=vec3(p.x,-p.y,z); vec3 light=normalize(vec3(-.45,.55,.72));
 float wrap=(dot(n,light)+.6)/1.6; float diff=.35+.65*clamp(wrap,0.,1.);
 float spec=pow(max(dot(reflect(-light,n),vec3(0.,0.,1.)),0.),12.)*.10;
 float rim=pow(1.-z,2.5)*.35;
 vec3 shaded=c*diff*(.75+.25*z)+vec3(spec)+c*rim;
 float fog=smoothstep(-1.2,1.,depthV)*.35+.65;
 float alpha=a*edge*fog; gl_FragColor=vec4(shaded*alpha,alpha); }`;
// Density-terrain overlay: contour + ridge polylines live in the 2D layout
// plane (z=0) and ride the same camera transform as the points. The terrain
// describes the dedicated 2D embedding only, so it fades out with dim (the
// 3D positions are a different embedding) and crossfades across view morphs.
const lineVertex = `attribute vec2 pos; attribute float alpha; attribute float hgt;
uniform float zoom; uniform vec2 pan; uniform float theta; uniform float phi;
uniform float relief; uniform float hscale;
varying float a;
void main(){ vec3 q=vec3(pos,hgt*hscale*relief);
 float ct=cos(theta),st=sin(theta),cp=cos(phi),sp=sin(phi);
 q=vec3(ct*q.x+st*q.z,sp*(st*q.x-ct*q.z)+cp*q.y,-cp*(st*q.x-ct*q.z)+sp*q.y);
 float depth=1.35-q.z*.24;
 gl_Position=vec4(q.xy*.88*zoom/depth+pan,q.z*.12,1.); a=alpha; }`;
const lineFragment = `precision mediump float; uniform vec3 col; uniform float master; varying float a;
void main(){ float al=a*master; gl_FragColor=vec4(col*al,al); }`;
const CONTOUR_COL: [number, number, number] = [1, 1, 1];
const RIDGE_COL: [number, number, number] = [0.886, 0.69, 0.29]; // hub gold
// Filament web: topic-tinted curves living in the embedding-3D space itself
// (the z3/c3 coordinates), so they render only as dim approaches volume and
// share the exact camera transform of the points.
const webVertex = `attribute vec3 pa; attribute vec3 pb; attribute float tEnd; attribute float side;
attribute vec3 col; attribute float den; attribute float alen;
uniform float zoom; uniform vec2 pan; uniform float theta; uniform float phi;
uniform float aspect; uniform float width;
varying vec3 c; varying float depthV; varying float dn; varying float arc; varying float edge;
// Camera shared with the points, factored out so both ends go through the
// identical transform — a ribbon whose two ends disagree about the camera
// shears.
vec4 project(vec3 p, float ct, float st, float cp, float sp){
 vec3 q=vec3(ct*p.x+st*p.z,sp*(st*p.x-ct*p.z)+cp*p.y,-cp*(st*p.x-ct*p.z)+sp*p.y);
 float depth=1.35-q.z*.24;
 return vec4(q.xy*.88*zoom/depth+pan,q.z*.12,depth); }
void main(){
 float ct=cos(theta),st=sin(theta),cp=cos(phi),sp=sin(phi);
 vec4 ca=project(pa,ct,st,cp,sp), cb=project(pb,ct,st,cp,sp);
 vec4 here=mix(ca,cb,tEnd);
 // Perpendicular in aspect-corrected clip space, so a ribbon keeps the same
 // apparent thickness whatever the window shape. Degenerate segments (both
 // ends landing on the same pixel) would normalize to NaN and blow the quad
 // across the screen, so they fall back to a fixed direction.
 vec2 d=(cb.xy-ca.xy)*vec2(aspect,1.);
 d = length(d) < 1e-6 ? vec2(1.,0.) : normalize(d);
 vec2 n=vec2(-d.y,d.x)/vec2(aspect,1.);
 // True geometric taper: thin strands stay thin instead of every filament
 // rendering as the same hairline. Divided by depth so ribbons foreshorten
 // with distance like the points do.
 // (not named "half" — that is a reserved word in GLSL ES and will not compile)
 float hw=width*(.35+.65*min(den*1.6,1.))/max(here.w,.35);
 // gl_Position.z carries q.z*.12, so this recovers the rotated depth the
 // fragment shader's fog expects. Taking the unrotated z here would fog the
 // strands by the wrong axis.
 depthV=here.z/.12;
 gl_Position=vec4(here.xy+n*hw*side,here.z,1.);
 c=col; dn=den; arc=alen; edge=side; }`;
const webFragment = `precision mediump float; uniform float master; uniform float time;
varying vec3 c; varying float depthV; varying float dn; varying float arc; varying float edge;
void main(){ float fog=smoothstep(-1.2,1.,depthV)*.35+.65;
 float al=master*fog*(.25+.75*min(dn*1.6,1.));  // strands taper where fog thins
 // Ribbons are geometry now, so nothing antialiases them for free the way
 // gl.LINES did. edge runs -1..1 across the quad; fading the last third keeps
 // the strand reading as a soft filament rather than a hard-edged bar.
 al*=1.-smoothstep(.55,1.,abs(edge));
 // Flow pulses (#107 feature A): brightness follows a wave running along the
 // strand's own arc length, so light appears to travel without any geometry
 // moving. 18 rad/unit puts ~2 pulses on a typical strand; with the speed set
 // JS-side one crosses it in about 3s. Multiplied in, so the density taper
 // above survives. Frozen phase when the caller passes a constant time
 // (prefers-reduced-motion).
 //
 // Deep troughs keep the moving crest visible on dim strands.
 al*=.65+.35*sin(arc*18.-time*4.5);
 // Trunks earn their glow from density.
 gl_FragColor=vec4(c*al*(1.1+1.3*dn),al); }`;
// Junction beacons: soft sprites where strands meet — the crossroads of
// the web, future anchor points for the galaxy view (issue #78).
const junctionVertex = `attribute vec3 pos;
uniform float zoom; uniform vec2 pan; uniform float theta; uniform float phi; uniform float dpr;
varying float depthV;
void main(){ vec3 q=pos;
 float ct=cos(theta),st=sin(theta),cp=cos(phi),sp=sin(phi);
 q=vec3(ct*q.x+st*q.z,sp*(st*q.x-ct*q.z)+cp*q.y,-cp*(st*q.x-ct*q.z)+sp*q.y);
 float depth=1.35-q.z*.24; depthV=q.z;
 gl_Position=vec4(q.xy*.88*zoom/depth+pan,q.z*.12,1.);
 gl_PointSize=clamp(13.*zoom/depth*dpr,4.,34.*dpr); }`;
const junctionFragment = `precision mediump float; uniform float master; varying float depthV;
void main(){ vec2 p=gl_PointCoord*2.-1.; float g=exp(-3.5*dot(p,p));
 float fog=smoothstep(-1.2,1.,depthV)*.35+.65; float al=g*master*fog;
 gl_FragColor=vec4(vec3(.99,.86,.55)*al,al); }`;
// Monte-Carlo fog splats: big soft Gaussian sprites, opacity carrying the
// sampled density. The level uniform is the threshold scrubber — splats
// below it fade out, so sweeping the level down replays bubble nucleation
// at the density peaks, inflation, and merging, read off the static field.
// The shell uniform blends the selection from that superlevel set (fill)
// to the thickened level set |den - level| < .06 — a pseudo-isosurface
// shell, the Monte-Carlo preview of a marching-cubes surface. The band
// half-width matches the rung-09 witness (scripts/plot_fog.py --shell).
const fogVertex = `attribute vec3 pos; attribute float den;
uniform float zoom; uniform vec2 pan; uniform float theta; uniform float phi; uniform float dpr;
varying float d; varying float depthV;
void main(){ vec3 q=pos;
 float ct=cos(theta),st=sin(theta),cp=cos(phi),sp=sin(phi);
 q=vec3(ct*q.x+st*q.z,sp*(st*q.x-ct*q.z)+cp*q.y,-cp*(st*q.x-ct*q.z)+sp*q.y);
 float depth=1.35-q.z*.24; depthV=q.z;
 gl_Position=vec4(q.xy*.88*zoom/depth+pan,q.z*.12,1.);
 gl_PointSize=clamp(30.*zoom/depth*dpr,6.,90.*dpr); d=den; }`;
const fogFragment = `precision mediump float; uniform float master; uniform float level; uniform float shell;
varying float d; varying float depthV;
void main(){ vec2 p=gl_PointCoord*2.-1.; float g=exp(-4.5*dot(p,p));
 float pass=smoothstep(level-.025,level+.025,d);
 float band=1.-smoothstep(.03,.06,abs(d-level));
 float sel=mix(pass,band,shell);
 float fogDepth=smoothstep(-1.2,1.,depthV)*.35+.65;
 // Gamma-lift the density before it drives colour or alpha: the median is
 // ~0.17, which the raw ramp renders near-black (same fix as punch() in
 // scripts/plot_assets.py, so hub and figures agree).
 float dl=pow(d,.72);
 float al=g*(.05+.34*dl)*sel*master*fogDepth;
 // 3-stop density ramp, monotone in lightness (magma-spirited):
 // deep indigo haze -> rose mid -> warm cream cores
 vec3 lo=vec3(.20,.16,.42); vec3 mid=vec3(.82,.32,.54); vec3 hi=vec3(1.,.94,.76);
 vec3 col=dl<.5 ? mix(lo,mid,dl*2.) : mix(mid,hi,(dl-.5)*2.);
 gl_FragColor=vec4(col*al,al); }`;
// Relief height of the density peak, in layout units (map spans about 2).
const HSCALE = 0.22;

// Render resolution: MAX_DPR > the display's native ratio supersamples
// (crisper strand lines and sprite edges at ~2.2x the fill cost on a
// retina panel). Drop to 2 if the fans ever notice; the idle-stop work
// in #101 is what keeps a static map from paying for it continuously.
const MAX_DPR = 3;
const pixelRatio = () => Math.min(devicePixelRatio || 1, MAX_DPR);
// Domain/subtopic ramp. SAT lifts chroma the same way the matplotlib
// figures do (scripts/plot_assets.py), so the hub and the published
// figures read as one palette; it runs inside rampColor so the legend
// swatches and the vertex buffers can never drift apart.
const ramp = ["#5b7cfa", "#2fb7c9", "#43c26a", "#d9a520", "#e8703a", "#e0507e", "#9d6bf0"];
const SAT = 1.3;
function saturate(c: [number, number, number]): [number, number, number] {
  const lum = 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
  return c.map((ch) => Math.max(0, Math.min(1, lum + (ch - lum) * SAT))) as [
    number,
    number,
    number,
  ];
}
const gray: [number, number, number] = [0.435, 0.427, 0.4];
const rgb = (hex: string): [number, number, number] =>
  [1, 3, 5].map((offset) => parseInt(hex.slice(offset, offset + 2), 16) / 255) as [
    number,
    number,
    number,
  ];
function rampColor(value: number): [number, number, number] {
  const x = Math.max(0, Math.min(0.9999, value)) * (ramp.length - 1);
  const i = Math.floor(x);
  const f = x - i;
  const a = rgb(ramp[i]);
  const b = rgb(ramp[i + 1]);
  return saturate([a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f]);
}
const css = (color: [number, number, number]) =>
  `rgb(${color.map((channel) => Math.round(channel * 255)).join(", ")})`;
// Ramp position of a domain (by size rank) and of a subtopic (its domain's
// position hue-shifted across +-0.08 by index-within-domain) — the single
// source of truth for both the vertex buffer and the legend swatches.
// Notes matching no bucket (#106). Not a topic, so it never takes a ramp
// slot — it renders grey, and it is excluded from the size ranking so that
// adding or losing unplaced mass cannot shift every other domain's hue.
export const UNPLACED_LABEL = "unplaced";
const isUnplaced = (data: MapData, index: number): boolean =>
  data.all.domains[index]?.label === UNPLACED_LABEL;

// Per-point birth position for the time machine (#107 D), as a quantile of
// the dated corpus rather than a normalized timestamp.
//
// The dates are not spread over the vault's life — 3832 of 3889 fall in one
// year, so under linear time half the corpus arrives after 95.7% of the
// scrubber's travel and the whole sweep happens in the last centimetre.
// Ranking makes the reveal uniform in notes revealed, which is the thing the
// scrubber is actually for. See docs/assets/07-time-machine/.
//
// Undated points return -1, a sentinel the shader reads as "always present".
// They are whole categories (project-note 0/71, pinterest, reddit, web, all
// 0%), so folding them in at t=0 would fabricate a history for one class of
// note and not another.
export function pointBirths(points: MapPoint[]): number[] {
  const stamps = points.map((point) => (point.d ? Date.parse(point.d) : Number.NaN));
  const dated = stamps.filter((t) => !Number.isNaN(t)).sort((a, b) => a - b);
  if (dated.length < 2) return stamps.map(() => -1);
  return stamps.map((t) => {
    if (Number.isNaN(t)) return -1;
    // Rank via binary search; ties share the lower bound so same-day notes
    // arrive together rather than being split by array order.
    let lo = 0;
    let hi = dated.length;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (dated[mid] < t) lo = mid + 1;
      else hi = mid;
    }
    return lo / (dated.length - 1);
  });
}

function domainPos(data: MapData, index: number): number {
  const order = data.all.domains
    .map((domain, i) => ({ i, n: domain.n }))
    .filter((item) => !isUnplaced(data, item.i))
    .sort((a, b) => b.n - a.n);
  const rank = order.findIndex((item) => item.i === index);
  return Math.max(0, rank) / Math.max(1, order.length - 1);
}
// Domain colour with the unplaced class folded in, so every caller that
// paints by domain agrees without restating the rule.
function domainColor(data: MapData, index: number): [number, number, number] {
  return isUnplaced(data, index) ? gray : rampColor(domainPos(data, index));
}
function subPos(data: MapData, index: number): number {
  const domain = data.all.groups[index]?.domain ?? -1;
  const siblings = data.all.groups.flatMap((group, i) => (group.domain === domain ? [i] : []));
  const k = siblings.indexOf(index);
  const spread = siblings.length > 1 ? (k / (siblings.length - 1) - 0.5) * 0.16 : 0;
  return Math.max(0, Math.min(0.9999, domainPos(data, domain) + spread));
}
export function mapDomainColor(data: MapData, index: number): string {
  return css(domainColor(data, index));
}
export function mapSubColor(data: MapData, index: number): string {
  const domain = data.all.groups[index]?.domain ?? -1;
  return css(isUnplaced(data, domain) ? gray : rampColor(subPos(data, index)));
}
export function mapGroupColor(data: MapData, view: "all" | "content", index: number): string {
  return view === "content" ? css(rampColor(index / 7)) : mapSubColor(data, index);
}

function shader(gl: WebGLRenderingContext, type: number, source: string) {
  const value = gl.createShader(type)!;
  gl.shaderSource(value, source);
  gl.compileShader(value);
  if (!gl.getShaderParameter(value, gl.COMPILE_STATUS))
    throw new Error(gl.getShaderInfoLog(value) || "shader compilation failed");
  return value;
}

// One intro per SPA session: remounting the route replays instantly.
let introPlayed = false;

type RenderedPoint = {
  point: MapPoint;
  p3a: number[];
  p3b: number[];
  p2a: number[];
  p2b: number[];
  group: number;
  domain: number;
  h2a: number;
  h2b: number;
};

export function mountMapRenderer(
  canvas: HTMLCanvasElement,
  data: MapData,
  onHover?: (hover?: MapHover) => void,
  labels?: HTMLElement,
  onFocus?: (focus: MapFocus) => void,
  leaders?: SVGSVGElement,
  opts?: { intro?: boolean },
): MapRenderer {
  const gl = canvas.getContext("webgl", { antialias: true, alpha: true, premultipliedAlpha: true });
  if (!gl) throw new Error("WebGL is unavailable in this browser");
  if ((gl.getParameter(gl.MAX_VERTEX_UNIFORM_VECTORS) as number) < 512)
    console.warn("map: vertex uniform budget below 512 vectors, focus arrays may not fit");
  const program = gl.createProgram()!;
  gl.attachShader(program, shader(gl, gl.VERTEX_SHADER, vertex));
  gl.attachShader(program, shader(gl, gl.FRAGMENT_SHADER, fragment));
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS))
    throw new Error(gl.getProgramInfoLog(program) || "program link failed");
  gl.useProgram(program);
  gl.enable(gl.BLEND);
  gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
  const buffer = gl.createBuffer()!;
  // --- terrain overlay resources (absent on pre-terrain map.json builds)
  let lineProgram: WebGLProgram | undefined;
  let lineU:
    | Record<
        "zoom" | "pan" | "theta" | "phi" | "col" | "master" | "relief" | "hscale",
        WebGLUniformLocation | null
      >
    | undefined;
  let linePos = 0;
  let lineAlpha = 0;
  let lineHgt = 0;
  type TerrainBuffers = {
    contours: WebGLBuffer;
    contourCount: number;
    ridges: WebGLBuffer;
    ridgeCount: number;
  };
  const terrainBuffers: Partial<Record<"all" | "content", TerrainBuffers>> = {};
  if (data.all.terrain || data.content.terrain) {
    lineProgram = gl.createProgram()!;
    gl.attachShader(lineProgram, shader(gl, gl.VERTEX_SHADER, lineVertex));
    gl.attachShader(lineProgram, shader(gl, gl.FRAGMENT_SHADER, lineFragment));
    gl.linkProgram(lineProgram);
    if (!gl.getProgramParameter(lineProgram, gl.LINK_STATUS))
      throw new Error(gl.getProgramInfoLog(lineProgram) || "terrain program link failed");
    linePos = gl.getAttribLocation(lineProgram, "pos");
    lineAlpha = gl.getAttribLocation(lineProgram, "alpha");
    lineHgt = gl.getAttribLocation(lineProgram, "hgt");
    lineU = {
      zoom: gl.getUniformLocation(lineProgram, "zoom"),
      pan: gl.getUniformLocation(lineProgram, "pan"),
      theta: gl.getUniformLocation(lineProgram, "theta"),
      phi: gl.getUniformLocation(lineProgram, "phi"),
      col: gl.getUniformLocation(lineProgram, "col"),
      master: gl.getUniformLocation(lineProgram, "master"),
      relief: gl.getUniformLocation(lineProgram, "relief"),
      hscale: gl.getUniformLocation(lineProgram, "hscale"),
    };
    const upload = (segments: number[]) => {
      const buf = gl.createBuffer()!;
      gl.bindBuffer(gl.ARRAY_BUFFER, buf);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(segments), gl.STATIC_DRAW);
      return buf;
    };
    const build = (terrain: MapTerrain | undefined, key: "all" | "content") => {
      if (!terrain) return;
      // GL_LINES pairs, 4 floats per vertex (x, y, alpha, height). Per-vertex
      // alpha bakes the contour level so one draw call renders the whole
      // nest; height lifts each ring to its level in relief mode. Ridge
      // vertices carry their own sampled density height.
      const contours: number[] = [];
      for (const c of terrain.contours) {
        const hz = terrain.fracs?.[c.lv] ?? 0;
        const a = 0.04 + c.lv * 0.011;
        for (let i = 0; i + 1 < c.path.length; i++)
          contours.push(
            c.path[i][0],
            c.path[i][1],
            a,
            hz,
            c.path[i + 1][0],
            c.path[i + 1][1],
            a,
            hz,
          );
      }
      const ridges: number[] = [];
      for (const r of terrain.ridges)
        for (let i = 0; i + 1 < r.length; i++)
          ridges.push(
            r[i][0],
            r[i][1],
            1,
            r[i][2] ?? 0,
            r[i + 1][0],
            r[i + 1][1],
            1,
            r[i + 1][2] ?? 0,
          );
      terrainBuffers[key] = {
        contours: upload(contours),
        contourCount: contours.length / 4,
        ridges: upload(ridges),
        ridgeCount: ridges.length / 4,
      };
    };
    build(data.all.terrain, "all");
    build(data.content.terrain, "content");
  }
  // --- filament web resources (absent on pre-web map.json builds)
  let webProgram: WebGLProgram | undefined;
  let webU:
    | Record<
        "zoom" | "pan" | "theta" | "phi" | "master" | "time" | "aspect" | "width",
        WebGLUniformLocation | null
      >
    | undefined;
  let webPos = 0;
  let webPosB = 0;
  let webTEnd = 0;
  let webSide = 0;
  let webCol = 0;
  let webDen = 0;
  let webAlen = 0;
  const webBuffers: Partial<Record<"all" | "content", { buf: WebGLBuffer; count: number }>> = {};
  let junctionProgram: WebGLProgram | undefined;
  let junctionU:
    | Record<"zoom" | "pan" | "theta" | "phi" | "dpr" | "master", WebGLUniformLocation | null>
    | undefined;
  let junctionPos = 0;
  const junctionBuffers: Partial<Record<"all" | "content", { buf: WebGLBuffer; count: number }>> =
    {};
  if (data.all.web || data.content.web) {
    webProgram = gl.createProgram()!;
    gl.attachShader(webProgram, shader(gl, gl.VERTEX_SHADER, webVertex));
    gl.attachShader(webProgram, shader(gl, gl.FRAGMENT_SHADER, webFragment));
    gl.linkProgram(webProgram);
    if (!gl.getProgramParameter(webProgram, gl.LINK_STATUS))
      throw new Error(gl.getProgramInfoLog(webProgram) || "web program link failed");
    webPos = gl.getAttribLocation(webProgram, "pa");
    webPosB = gl.getAttribLocation(webProgram, "pb");
    webTEnd = gl.getAttribLocation(webProgram, "tEnd");
    webSide = gl.getAttribLocation(webProgram, "side");
    webCol = gl.getAttribLocation(webProgram, "col");
    webDen = gl.getAttribLocation(webProgram, "den");
    webAlen = gl.getAttribLocation(webProgram, "alen");
    webU = {
      time: gl.getUniformLocation(webProgram, "time"),
      aspect: gl.getUniformLocation(webProgram, "aspect"),
      width: gl.getUniformLocation(webProgram, "width"),
      zoom: gl.getUniformLocation(webProgram, "zoom"),
      pan: gl.getUniformLocation(webProgram, "pan"),
      theta: gl.getUniformLocation(webProgram, "theta"),
      phi: gl.getUniformLocation(webProgram, "phi"),
      master: gl.getUniformLocation(webProgram, "master"),
    };
    const build = (web: MapWeb | undefined, key: "all" | "content") => {
      if (!web) return;
      // Ribbons (#107 feature B), not lines. Every thick line on a GPU is
      // triangles in costume: gl.LINES cannot vary width, so each segment is
      // expanded into a quad — two triangles, six vertices — and widened in
      // the vertex shader along the screen-space perpendicular. That is what
      // buys a true geometric taper from density instead of a uniform hairline.
      //
      // 13 floats per vertex, stride 52:
      //   a(3) b(3) t(1) side(1) rgb(3) den(1) alen(1)
      // Both endpoints ride every vertex so the shader can compute the
      // segment's direction; t picks which end this vertex sits at, side which
      // edge of the ribbon. Colour, density and arc length are this vertex's
      // own, so the existing varyings still blend along the strand.
      const colorOf = (label: number): [number, number, number] =>
        label < 0 ? gray : key === "all" ? domainColor(data, label) : rampColor(label / 7);
      const segments: number[] = [];
      for (const fil of web.filaments) {
        // Distance travelled along this strand, in layout units. Absolute and
        // never normalised per strand: a percentage would make one pulse cross
        // a short strand and a long one in the same time, so light would crawl
        // down the spine and race down the stubs. Trustworthy because the
        // predictor-corrector tracer emits ordered, near-uniformly spaced
        // vertices (ytk/ridges.py::trace_filaments).
        let travelled = 0;
        for (let i = 0; i + 1 < fil.length; i++) {
          const a = fil[i];
          const b = fil[i + 1];
          const step = Math.hypot(b[0] - a[0], b[1] - a[1], b[2] - a[2]);
          const ends = [
            { t: 0, col: colorOf(a[3]), den: a[4] ?? 1, alen: travelled },
            { t: 1, col: colorOf(b[3]), den: b[4] ?? 1, alen: travelled + step },
          ] as const;
          const vertex = (which: 0 | 1, side: number) => {
            const e = ends[which];
            segments.push(a[0], a[1], a[2], b[0], b[1], b[2], e.t, side, ...e.col, e.den, e.alen);
          };
          // Two triangles over the quad, consistent winding.
          vertex(0, -1);
          vertex(0, 1);
          vertex(1, -1);
          vertex(1, -1);
          vertex(0, 1);
          vertex(1, 1);
          travelled += step;
        }
      }
      if (!segments.length) return;
      const buf = gl.createBuffer()!;
      gl.bindBuffer(gl.ARRAY_BUFFER, buf);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(segments), gl.STATIC_DRAW);
      webBuffers[key] = { buf, count: segments.length / 13 };
    };
    build(data.all.web, "all");
    build(data.content.web, "content");
    junctionProgram = gl.createProgram()!;
    gl.attachShader(junctionProgram, shader(gl, gl.VERTEX_SHADER, junctionVertex));
    gl.attachShader(junctionProgram, shader(gl, gl.FRAGMENT_SHADER, junctionFragment));
    gl.linkProgram(junctionProgram);
    if (!gl.getProgramParameter(junctionProgram, gl.LINK_STATUS))
      throw new Error(gl.getProgramInfoLog(junctionProgram) || "junction program link failed");
    junctionPos = gl.getAttribLocation(junctionProgram, "pos");
    junctionU = {
      zoom: gl.getUniformLocation(junctionProgram, "zoom"),
      pan: gl.getUniformLocation(junctionProgram, "pan"),
      theta: gl.getUniformLocation(junctionProgram, "theta"),
      phi: gl.getUniformLocation(junctionProgram, "phi"),
      dpr: gl.getUniformLocation(junctionProgram, "dpr"),
      master: gl.getUniformLocation(junctionProgram, "master"),
    };
    const buildJunctions = (web: MapWeb | undefined, key: "all" | "content") => {
      if (!web?.junctions?.length) return;
      const buf = gl.createBuffer()!;
      gl.bindBuffer(gl.ARRAY_BUFFER, buf);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(web.junctions.flat()), gl.STATIC_DRAW);
      junctionBuffers[key] = { buf, count: web.junctions.length };
    };
    buildJunctions(data.all.web, "all");
    buildJunctions(data.content.web, "content");
  }
  // --- fog splat resources (absent on pre-fog map.json builds)
  let fogProgram: WebGLProgram | undefined;
  let fogU:
    | Record<
        "zoom" | "pan" | "theta" | "phi" | "dpr" | "master" | "level" | "shell",
        WebGLUniformLocation | null
      >
    | undefined;
  let fogPos = 0;
  let fogDen = 0;
  const fogBuffers: Partial<Record<"all" | "content", { buf: WebGLBuffer; count: number }>> = {};
  if (data.all.fog || data.content.fog) {
    fogProgram = gl.createProgram()!;
    gl.attachShader(fogProgram, shader(gl, gl.VERTEX_SHADER, fogVertex));
    gl.attachShader(fogProgram, shader(gl, gl.FRAGMENT_SHADER, fogFragment));
    gl.linkProgram(fogProgram);
    if (!gl.getProgramParameter(fogProgram, gl.LINK_STATUS))
      throw new Error(gl.getProgramInfoLog(fogProgram) || "fog program link failed");
    fogPos = gl.getAttribLocation(fogProgram, "pos");
    fogDen = gl.getAttribLocation(fogProgram, "den");
    fogU = {
      zoom: gl.getUniformLocation(fogProgram, "zoom"),
      pan: gl.getUniformLocation(fogProgram, "pan"),
      theta: gl.getUniformLocation(fogProgram, "theta"),
      phi: gl.getUniformLocation(fogProgram, "phi"),
      dpr: gl.getUniformLocation(fogProgram, "dpr"),
      master: gl.getUniformLocation(fogProgram, "master"),
      level: gl.getUniformLocation(fogProgram, "level"),
      shell: gl.getUniformLocation(fogProgram, "shell"),
    };
    const build = (fogData: MapFog | undefined, key: "all" | "content") => {
      if (!fogData?.splats.length) return;
      const flat = fogData.splats.flat();
      const buf = gl.createBuffer()!;
      gl.bindBuffer(gl.ARRAY_BUFFER, buf);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(flat), gl.STATIC_DRAW);
      fogBuffers[key] = { buf, count: fogData.splats.length };
    };
    build(data.all.fog, "all");
    build(data.content.fog, "content");
  }
  // Bilinear samplers over the terrain height grids lift points onto the
  // relief surface without any per-point data in the payload.
  const heightSampler = (terrain?: MapTerrain) => {
    const g = terrain?.grid;
    if (!g) return () => 0;
    return (x: number, y: number) => {
      const fx = ((x - g.x0) / (g.x1 - g.x0)) * (g.nx - 1);
      const fy = ((y - g.y0) / (g.y1 - g.y0)) * (g.ny - 1);
      if (fx < 0 || fy < 0 || fx > g.nx - 1 || fy > g.ny - 1) return 0;
      const i = Math.min(g.nx - 2, Math.floor(fx)),
        j = Math.min(g.ny - 2, Math.floor(fy));
      const u = fx - i,
        v = fy - j;
      const z = (jj: number, ii: number) => g.z[jj * g.nx + ii] ?? 0;
      return (
        (1 - u) * (1 - v) * z(j, i) +
        u * (1 - v) * z(j, i + 1) +
        (1 - u) * v * z(j + 1, i) +
        u * v * z(j + 1, i + 1)
      );
    };
  };
  const heightAll = heightSampler(data.all.terrain);
  const heightContent = heightSampler(data.content.terrain);
  const position0 = gl.getAttribLocation(program, "p0");
  const position1 = gl.getAttribLocation(program, "p1");
  const flat0 = gl.getAttribLocation(program, "q0");
  const flat1 = gl.getAttribLocation(program, "q1");
  const color0 = gl.getAttribLocation(program, "color0");
  const color1 = gl.getAttribLocation(program, "color1");
  const colorSub = gl.getAttribLocation(program, "colorSub");
  const alpha0 = gl.getAttribLocation(program, "alpha0");
  const alpha1 = gl.getAttribLocation(program, "alpha1");
  const size = gl.getAttribLocation(program, "size");
  const grp = gl.getAttribLocation(program, "grp");
  const dm = gl.getAttribLocation(program, "dm");
  const phaseAttr = gl.getAttribLocation(program, "phase");
  const hgt0Attr = gl.getAttribLocation(program, "hgt0");
  const hgt1Attr = gl.getAttribLocation(program, "hgt1");
  const idAttr = gl.getAttribLocation(program, "idBirth");
  const pickModeU = gl.getUniformLocation(program, "pickMode");
  const pickPadU = gl.getUniformLocation(program, "pickPad");
  const reliefU = gl.getUniformLocation(program, "relief");
  const hscaleU = gl.getUniformLocation(program, "hscale");
  const focDomAU = gl.getUniformLocation(program, "focDomA[0]");
  const focDomBU = gl.getUniformLocation(program, "focDomB[0]");
  const focSubAU = gl.getUniformLocation(program, "focSubA[0]");
  const focSubBU = gl.getUniformLocation(program, "focSubB[0]");
  const focusTU = gl.getUniformLocation(program, "focusT");
  const levelU = gl.getUniformLocation(program, "level");
  const subColorTU = gl.getUniformLocation(program, "subColorT");
  const introTU = gl.getUniformLocation(program, "introT");
  const clockU = gl.getUniformLocation(program, "clock");
  const timeU = gl.getUniformLocation(program, "time");
  const morphUniform = gl.getUniformLocation(program, "morph");
  const dimUniform = gl.getUniformLocation(program, "dim");
  const zoom = gl.getUniformLocation(program, "zoom");
  const pan = gl.getUniformLocation(program, "pan");
  const theta = gl.getUniformLocation(program, "theta");
  const phi = gl.getUniformLocation(program, "phi");
  const dpr = gl.getUniformLocation(program, "dpr");
  let view: "all" | "content" = "all";
  let frame = 0;
  let scale = 1;
  let scaleTarget = 1;
  let flyItem: RenderedPoint | undefined;
  let offset: [number, number] = [0, 0];
  let drag: { x: number; y: number } | undefined;
  let moved = 0;
  let orbit = false;
  let samples: VelocitySample[] = [];
  let momentum: { vx: number; vy: number } = { vx: 0, vy: 0 };
  const killMomentum = () => {
    momentum = { vx: 0, vy: 0 };
    samples = [];
  };
  // `?motion=on` overrides the OS preference for this page load only. The
  // default stays the accessibility setting — this is an explicit, per-visit
  // opt-in for looking at motion features on a machine that has reduce-motion
  // switched on system-wide, not a way to ignore the preference.
  const forceMotion = new URLSearchParams(location.search).get("motion") === "on";
  const reduceMotion = !forceMotion && matchMedia("(prefers-reduced-motion: reduce)").matches;
  let angle = 0.5;
  let tilt = 0.3;
  let signalOnly = false;
  let recentOnly = false;
  // Content lens (#106): dims session/memory points on the everything view so
  // consumed media's neighbourhoods read in place, rather than having to
  // switch to the content view and lose the surrounding context.
  let mediaOnly = false;
  let geometryDirty = true;
  let pointCount = 0;
  let renderedPoints: RenderedPoint[] = [];
  let hoveredPoint: MapPoint | undefined;
  let labelsDirty = true;
  let labelItems: Array<{
    c3: number[];
    c2: number[];
    radius: number;
    node: HTMLDivElement;
    line?: SVGLineElement | undefined;
    rank: number;
    n: number;
  }> = [];
  let roadPick: ((point: MapPoint) => void) | undefined;
  let route: RoadWaypointRef[] | undefined;
  let roadGroup: SVGGElement | undefined;
  let roadPath: SVGPathElement | undefined;
  let roadDots: SVGCircleElement[] = [];
  let morph = location.hash === "#content" ? 1 : 0;
  let morphTarget = morph;
  let dimVal = location.hash === "#2d" ? 0 : 1;
  let dimTarget = dimVal;
  // With terrain on, "3d" means relief (2D layout + density height), not the
  // embedding-3D morph: dim is forced flat and relief rises instead.
  let requestedDim = dimTarget;
  let reliefT = 0;
  let reliefTarget = 0;
  const retargetDims = () => {
    dimTarget = terrainOn ? 0 : requestedDim;
    reliefTarget = terrainOn && requestedDim === 1 ? 1 : 0;
  };
  let legendOpen = true;
  let focus: MapFocus = {};
  let hover: MapFocus | undefined;
  let hiddenDoms = new Set<number>();
  const nDom = data.all.domains.length;
  const nSub = data.all.groups.length;
  if (nDom > 32 || nSub > 96)
    console.warn(`map: hierarchy exceeds shader capacity (${nDom} domains, ${nSub} subtopics)`);
  let focA: { dom: Float32Array; sub: Float32Array } = {
    dom: new Float32Array(nDom).fill(1),
    sub: new Float32Array(nSub).fill(1),
  };
  let focB: { dom: Float32Array; sub: Float32Array } = {
    dom: new Float32Array(nDom).fill(1),
    sub: new Float32Array(nSub).fill(1),
  };
  let focusT = 1;
  let subColorT = 0;
  let terrainOn = false;
  let terrainT = 0;
  let webOn = false;
  let webT = 0;
  let fogOn = false;
  let fogT = 0;
  let fogLevel = 0;
  let fogShell = false;
  let shellT = 0;
  const intro = (opts?.intro ?? false) && !introPlayed;
  if (intro) {
    introPlayed = true;
    canvas.dataset.intro = "1";
  }
  let introT = intro ? 0 : 1;
  // 1 = the whole corpus is present, so the time machine is inert until the
  // scrubber moves and nothing about the default render changes.
  let clock = 1;
  const phases = pointPhases(data.points);
  const births = pointBirths(data.points);
  // Colours, not ramp positions: `unplaced` has no position on the ramp, and
  // its subtopics inherit the grey rather than falling back to the hot end.
  const domColorArr = data.all.domains.map((_, index) => domainColor(data, index));
  const subColorArr = data.all.groups.map((group, index) =>
    isUnplaced(data, group.domain ?? -1) ? gray : rampColor(subPos(data, index)),
  );
  // Themes act as single-level domains in the content view; theme dims ride
  // both arrays because content points carry the theme in grp AND dm.
  // The shared domain array bounds the number of theme targets.
  const contentTargets = () => {
    const n = data.content.groups.length;
    const dom = new Float32Array(nDom).fill(1);
    const sub = new Float32Array(nSub).fill(1);
    for (let d = 0; d < n && d < nDom; d++)
      dom[d] = focus.dom === undefined || (hover?.dom ?? focus.dom) === d ? 1 : DIM;
    if (hover?.dom !== undefined)
      for (let d = 0; d < n && d < nDom; d++) dom[d] = hover.dom === d ? 1 : DIM;
    for (let d = 0; d < n && d < nSub; d++) sub[d] = dom[d];
    return { dom, sub };
  };
  const retarget = () => {
    // Freeze the currently displayed value as the new A so mid-flight
    // retargets do not jump: the per-point ramp is approximated with the
    // group-level ramp(focusT).
    const t = ease(Math.max(0, Math.min(1, focusT)));
    for (let i = 0; i < nDom; i++) focA.dom[i] = focA.dom[i] + (focB.dom[i] - focA.dom[i]) * t;
    for (let i = 0; i < nSub; i++) focA.sub[i] = focA.sub[i] + (focB.sub[i] - focA.sub[i]) * t;
    const view2 = view === "content";
    focB = view2 ? contentTargets() : groupTargets(nDom, data.all.groups, focus, hover, hiddenDoms);
    focusT = 0;
  };

  const lerp3 = (a: number[], b: number[], t: number) => [
    a[0] + (b[0] - a[0]) * t,
    a[1] + (b[1] - a[1]) * t,
    a[2] + (b[2] - a[2]) * t,
  ];
  // flat<->volume blend of a morphed 3D position and its 2D counterpart
  const blend = (p3: number[], p2: number[]) => [
    p2[0] + (p3[0] - p2[0]) * dimVal,
    p2[1] + (p3[1] - p2[1]) * dimVal,
    p3[2] * dimVal,
  ];
  const morph3 = (item: RenderedPoint) => lerp3(item.p3a, item.p3b, morph);
  const morph2 = (item: RenderedPoint) => [
    item.p2a[0] + (item.p2b[0] - item.p2a[0]) * morph,
    item.p2a[1] + (item.p2b[1] - item.p2a[1]) * morph,
  ];
  const worldOf = (item: RenderedPoint) => {
    const w = blend(morph3(item), morph2(item));
    w[2] += (item.h2a + (item.h2b - item.h2a) * morph) * HSCALE * reliefT;
    return w;
  };
  // rotation is live in either 3D: the embedding volume (dim) or the relief
  const project = (world: number[]) => {
    const [x, y, z] = world;
    const rot = Math.max(dimVal, reliefT);
    const ea = angle * rot,
      et = tilt * rot;
    const ct = Math.cos(ea),
      st = Math.sin(ea),
      cp = Math.cos(et),
      sp = Math.sin(et);
    const rx = ct * x + st * z;
    const rz = -st * x + ct * z;
    const ry = sp * -rz + cp * y;
    const depth = 1.35 - (cp * rz + sp * y) * 0.24;
    return [
      (((rx * 0.88 * scale) / depth + offset[0] + 1) * canvas.clientWidth) / 2,
      ((1 - ((ry * 0.88 * scale) / depth + offset[1])) * canvas.clientHeight) / 2,
      depth,
    ];
  };

  const resize = () => {
    const ratio = pixelRatio();
    canvas.width = innerWidth * ratio;
    canvas.height = innerHeight * ratio;
    canvas.style.width = `${innerWidth}px`;
    canvas.style.height = `${innerHeight}px`;
    gl.viewport(0, 0, canvas.width, canvas.height);
  };
  let lastDrawTime = 0;
  const draw = (time: number) => {
    if (!pickPass) lastDrawTime = time;
    if (geometryDirty) {
      renderedPoints = [];
      const points = data.points.flatMap((point, index) => {
        const p3a = point.z3;
        const p3b = point.c3 ?? point.z3;
        const p2a = [point.x, point.y];
        const p2b = [point.cx ?? point.x, point.cy ?? point.y];
        const days = point.d
          ? (Date.parse(document.lastModified) - Date.parse(point.d)) / 86_400_000
          : Infinity;
        const recency = recentOnly ? Math.max(0.12, Math.pow(0.5, Math.max(0, days) / 90)) : 1;
        // A content point is one the content view also places — read off the
        // payload rather than restating CONTENT_CATS here, where it would
        // silently drift from ytk/mapdomains.py.
        const isContent = point.cx !== undefined;
        const lens = mediaOnly && !isContent ? 0.04 : recency;
        const sig = signalOnly && point.r < 1 ? 0.04 : lens;
        const alphaFor = (base: number) => (sig === 0.04 ? 0.04 : base * sig);
        const domColor = point.dom >= 0 ? (domColorArr[point.dom] ?? gray) : gray;
        const subColor = point.g >= 0 ? (subColorArr[point.g] ?? domColor) : domColor;
        const themeColor = point.th !== undefined && point.th >= 0 ? rampColor(point.th / 7) : gray;
        const alpha0 = alphaFor(point.g < 0 ? 0.4 : 1);
        const alpha1 = alphaFor(point.c3 ? 0.95 : 0);
        const group = pointGroup(point, view);
        const domain = pointDomain(point, view);
        const h2a = heightAll(point.x, point.y);
        const h2b =
          point.cx !== undefined && point.cy !== undefined ? heightContent(point.cx, point.cy) : 0;
        renderedPoints.push({ point, p3a, p3b, p2a, p2b, group, domain, h2a, h2b });
        return [
          ...p3a,
          ...p3b,
          ...p2a,
          ...p2b,
          ...domColor,
          ...themeColor,
          ...subColor,
          alpha0,
          alpha1,
          3.2 + point.r * 1.8 + (point.c3 ? 0.8 : 0),
          group,
          domain,
          phases[index],
          h2a,
          h2b,
          // 1-based so 0 stays reserved for "background" in the pick buffer.
          // renderedPoints is pushed in this same order, so decoding id - 1
          // indexes straight back into it.
          renderedPoints.length,
          births[index],
        ];
      });
      pointCount = points.length / 29;
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(points), gl.STATIC_DRAW);
      geometryDirty = false;
    }
    const drawSet = (buf: WebGLBuffer, count: number) => {
      gl.bindBuffer(gl.ARRAY_BUFFER, buf);
      gl.enableVertexAttribArray(position0);
      gl.vertexAttribPointer(position0, 3, gl.FLOAT, false, 116, 0);
      gl.enableVertexAttribArray(position1);
      gl.vertexAttribPointer(position1, 3, gl.FLOAT, false, 116, 12);
      gl.enableVertexAttribArray(flat0);
      gl.vertexAttribPointer(flat0, 2, gl.FLOAT, false, 116, 24);
      gl.enableVertexAttribArray(flat1);
      gl.vertexAttribPointer(flat1, 2, gl.FLOAT, false, 116, 32);
      gl.enableVertexAttribArray(color0);
      gl.vertexAttribPointer(color0, 3, gl.FLOAT, false, 116, 40);
      gl.enableVertexAttribArray(color1);
      gl.vertexAttribPointer(color1, 3, gl.FLOAT, false, 116, 52);
      gl.enableVertexAttribArray(colorSub);
      gl.vertexAttribPointer(colorSub, 3, gl.FLOAT, false, 116, 64);
      gl.enableVertexAttribArray(alpha0);
      gl.vertexAttribPointer(alpha0, 1, gl.FLOAT, false, 116, 76);
      gl.enableVertexAttribArray(alpha1);
      gl.vertexAttribPointer(alpha1, 1, gl.FLOAT, false, 116, 80);
      gl.enableVertexAttribArray(size);
      gl.vertexAttribPointer(size, 1, gl.FLOAT, false, 116, 84);
      gl.enableVertexAttribArray(grp);
      gl.vertexAttribPointer(grp, 1, gl.FLOAT, false, 116, 88);
      gl.enableVertexAttribArray(dm);
      gl.vertexAttribPointer(dm, 1, gl.FLOAT, false, 116, 92);
      gl.enableVertexAttribArray(phaseAttr);
      gl.vertexAttribPointer(phaseAttr, 1, gl.FLOAT, false, 116, 96);
      gl.enableVertexAttribArray(hgt0Attr);
      gl.vertexAttribPointer(hgt0Attr, 1, gl.FLOAT, false, 116, 100);
      gl.enableVertexAttribArray(hgt1Attr);
      gl.vertexAttribPointer(hgt1Attr, 1, gl.FLOAT, false, 116, 104);
      gl.enableVertexAttribArray(idAttr);
      // Two floats, one attribute slot: id at 108, birth at 112.
      gl.vertexAttribPointer(idAttr, 2, gl.FLOAT, false, 116, 108);
      gl.drawArrays(gl.POINTS, 0, count);
    };
    const contentView = view === "content";
    const level = !contentView && focusLevel(focus) !== "overview" ? 1 : 0;
    const rot = Math.max(dimVal, reliefT);
    const ea = angle * rot;
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    // terrain underlay: drawn before the points, faded by dim (it describes
    // the 2D layout only) and crossfaded between the two views' layouts
    if (!pickPass && lineProgram && lineU && terrainT > 0.01 && dimVal < 0.99) {
      gl.useProgram(lineProgram);
      gl.uniform1f(lineU.zoom, scale);
      gl.uniform2f(lineU.pan, offset[0], offset[1]);
      gl.uniform1f(lineU.theta, ea);
      gl.uniform1f(lineU.phi, tilt * rot);
      gl.uniform1f(lineU.relief, reliefT);
      gl.uniform1f(lineU.hscale, HSCALE);
      for (const key of ["all", "content"] as const) {
        const weight = key === "all" ? 1 - morph : morph;
        const bufs = terrainBuffers[key];
        if (!bufs || weight <= 0.01) continue;
        const master = terrainT * (1 - dimVal) * weight;
        const drawLines = (
          buf: WebGLBuffer,
          count: number,
          col: [number, number, number],
          mult: number,
        ) => {
          if (!count) return;
          gl.bindBuffer(gl.ARRAY_BUFFER, buf);
          gl.enableVertexAttribArray(linePos);
          gl.vertexAttribPointer(linePos, 2, gl.FLOAT, false, 16, 0);
          gl.enableVertexAttribArray(lineAlpha);
          gl.vertexAttribPointer(lineAlpha, 1, gl.FLOAT, false, 16, 8);
          gl.enableVertexAttribArray(lineHgt);
          gl.vertexAttribPointer(lineHgt, 1, gl.FLOAT, false, 16, 12);
          gl.uniform3f(lineU!.col, col[0], col[1], col[2]);
          gl.uniform1f(lineU!.master, master * mult);
          gl.drawArrays(gl.LINES, 0, count);
        };
        drawLines(bufs.contours, bufs.contourCount, CONTOUR_COL, 0.9);
        drawLines(bufs.ridges, bufs.ridgeCount, RIDGE_COL, 0.42);
      }
      gl.useProgram(program);
    }
    // fog splats: drawn first (behind web and points), embedding-3D only
    if (!pickPass && fogProgram && fogU && fogT > 0.01 && dimVal > 0.01) {
      gl.useProgram(fogProgram);
      gl.uniform1f(fogU.zoom, scale);
      gl.uniform2f(fogU.pan, offset[0], offset[1]);
      gl.uniform1f(fogU.theta, ea);
      gl.uniform1f(fogU.phi, tilt * rot);
      gl.uniform1f(fogU.dpr, pixelRatio());
      gl.uniform1f(fogU.level, fogLevel);
      gl.uniform1f(fogU.shell, shellT);
      for (const key of ["all", "content"] as const) {
        const weight = key === "all" ? 1 - morph : morph;
        const bufs = fogBuffers[key];
        if (!bufs || weight <= 0.01) continue;
        gl.bindBuffer(gl.ARRAY_BUFFER, bufs.buf);
        gl.enableVertexAttribArray(fogPos);
        gl.vertexAttribPointer(fogPos, 3, gl.FLOAT, false, 16, 0);
        gl.enableVertexAttribArray(fogDen);
        gl.vertexAttribPointer(fogDen, 1, gl.FLOAT, false, 16, 12);
        gl.uniform1f(fogU.master, fogT * dimVal * weight);
        gl.drawArrays(gl.POINTS, 0, bufs.count);
      }
      gl.useProgram(program);
    }
    // filament web: lives in the embedding-3D coordinates, so it appears
    // only as dim approaches volume (and relief mode, which forces dim flat,
    // hides it automatically)
    if (!pickPass && webProgram && webU && webT > 0.01 && dimVal > 0.01) {
      gl.useProgram(webProgram);
      // A frozen clock leaves the pulse standing still rather than removing
      // it, so reduced motion keeps the strands' brightness variation without
      // anything travelling. It also lets animating() park the loop, since
      // nothing is changing frame to frame.
      gl.uniform1f(webU.time, reduceMotion ? 0 : time);
      // Ribbon width in clip units. Aspect keeps the thickness even on a wide
      // window; without it a strand running horizontally would render thinner
      // than the same strand running vertically.
      gl.uniform1f(webU.aspect, canvas.clientWidth / Math.max(canvas.clientHeight, 1));
      gl.uniform1f(webU.width, 0.0075);
      gl.uniform1f(webU.zoom, scale);
      gl.uniform2f(webU.pan, offset[0], offset[1]);
      gl.uniform1f(webU.theta, ea);
      gl.uniform1f(webU.phi, tilt * rot);
      for (const key of ["all", "content"] as const) {
        const weight = key === "all" ? 1 - morph : morph;
        const bufs = webBuffers[key];
        if (!bufs || weight <= 0.01) continue;
        gl.bindBuffer(gl.ARRAY_BUFFER, bufs.buf);
        gl.enableVertexAttribArray(webPos);
        // stride 52: a(0) b(12) tEnd(24) side(28) rgb(32) den(44) alen(48)
        gl.vertexAttribPointer(webPos, 3, gl.FLOAT, false, 52, 0);
        gl.enableVertexAttribArray(webPosB);
        gl.vertexAttribPointer(webPosB, 3, gl.FLOAT, false, 52, 12);
        gl.enableVertexAttribArray(webTEnd);
        gl.vertexAttribPointer(webTEnd, 1, gl.FLOAT, false, 52, 24);
        gl.enableVertexAttribArray(webSide);
        gl.vertexAttribPointer(webSide, 1, gl.FLOAT, false, 52, 28);
        gl.enableVertexAttribArray(webCol);
        gl.vertexAttribPointer(webCol, 3, gl.FLOAT, false, 52, 32);
        gl.enableVertexAttribArray(webDen);
        gl.vertexAttribPointer(webDen, 1, gl.FLOAT, false, 52, 44);
        gl.enableVertexAttribArray(webAlen);
        gl.vertexAttribPointer(webAlen, 1, gl.FLOAT, false, 52, 48);
        gl.uniform1f(webU.master, webT * dimVal * weight * 0.9);
        gl.drawArrays(gl.TRIANGLES, 0, bufs.count);
      }
      if (junctionProgram && junctionU) {
        gl.useProgram(junctionProgram);
        gl.uniform1f(junctionU.zoom, scale);
        gl.uniform2f(junctionU.pan, offset[0], offset[1]);
        gl.uniform1f(junctionU.theta, ea);
        gl.uniform1f(junctionU.phi, tilt * rot);
        gl.uniform1f(junctionU.dpr, pixelRatio());
        for (const key of ["all", "content"] as const) {
          const weight = key === "all" ? 1 - morph : morph;
          const bufs = junctionBuffers[key];
          if (!bufs || weight <= 0.01) continue;
          gl.bindBuffer(gl.ARRAY_BUFFER, bufs.buf);
          gl.enableVertexAttribArray(junctionPos);
          gl.vertexAttribPointer(junctionPos, 3, gl.FLOAT, false, 12, 0);
          gl.uniform1f(junctionU.master, webT * dimVal * weight * 0.75);
          gl.drawArrays(gl.POINTS, 0, bufs.count);
        }
      }
      gl.useProgram(program);
    }
    // Uniform locations are program-specific, so bind the point program even
    // when every optional layer is disabled.
    gl.useProgram(program);
    gl.uniform1f(morphUniform, morph);
    gl.uniform1f(dimUniform, dimVal);
    gl.uniform1f(zoom, scale);
    gl.uniform2f(pan, offset[0], offset[1]);
    gl.uniform1f(theta, ea);
    gl.uniform1f(phi, tilt * rot);
    gl.uniform1f(reliefU, reliefT);
    gl.uniform1f(hscaleU, HSCALE);
    gl.uniform1f(dpr, pixelRatio());
    gl.uniform1fv(focDomAU, focA.dom);
    gl.uniform1fv(focDomBU, focB.dom);
    gl.uniform1fv(focSubAU, focA.sub);
    gl.uniform1fv(focSubBU, focB.sub);
    gl.uniform1f(focusTU, focusT);
    gl.uniform1f(levelU, level);
    gl.uniform1f(pickModeU, pickPass ? 1 : 0);
    gl.uniform1f(pickPadU, pickPass ? PICK_PAD * pixelRatio() : 0);
    gl.uniform1f(subColorTU, subColorT);
    gl.uniform1f(introTU, introT);
    gl.uniform1f(clockU, clock);
    gl.uniform1f(timeU, time);
    drawSet(buffer, pointCount);
  };
  // Off-screen colour-ID pass (#101 fix 2). The GPU already worked out which
  // pixel every point covers in order to draw it; picking reads that answer
  // back instead of re-deriving it on the CPU for all ~4k points per
  // mousemove. Cost stops scaling with the corpus.
  //
  // PICK_PAD keeps hovering as forgiving as the old 12px-radius scan: the
  // sprite is grown in the pick pass only, so the hit area survives while the
  // visible size does not change.
  //
  // Kept small on purpose. Forgiveness comes from the block search below, not
  // from inflating sprites: padding them to a 12px radius made every crowded
  // neighbourhood overlap, and overlaps resolve by draw order rather than by
  // distance. scripts/plot_picking.py measured that at 647 of 963 hits landing
  // on a different point. A couple of pixels only guarantees the smallest
  // points (2.4px across) paint enough to be found. See docs/assets/02-picking/.
  // --- bloom ---------------------------------------------------------------
  // Four steps, all of them arithmetic: draw the scene into a texture, keep
  // only what is bright, blur that, add it back. Constants were dialled in
  // against a real captured frame in labs/bloom_tuning.py rather than guessed
  // here — the notebook runs this same pipeline in numpy.
  //
  const BLOOM_THRESHOLD = 0.26;
  const BLOOM_KNEE = 0.14;
  const BLOOM_SIGMA = 9.5; // px at full resolution
  const BLOOM_PASSES = 2;
  const BLOOM_DOWNSAMPLE = 2;
  const BLOOM_INTENSITY = 1.45;
  // `?bloom=off` isolates the unprocessed scene without a rebuild.
  const bloomOff = new URLSearchParams(location.search).get("bloom") === "off";

  const PICK_PAD = 2;
  // The old scan's tolerance, now the block-read radius.
  const SCAN_RADIUS = 12;
  let pickPass = false;
  let pickFb: WebGLFramebuffer | null = null;
  let pickTex: WebGLTexture | null = null;
  let pickW = 0;
  let pickH = 0;
  const pickTarget = () => {
    const w = Math.max(1, gl.drawingBufferWidth);
    const h = Math.max(1, gl.drawingBufferHeight);
    if (pickFb && pickW === w && pickH === h) return;
    if (pickTex) gl.deleteTexture(pickTex);
    if (pickFb) gl.deleteFramebuffer(pickFb);
    pickW = w;
    pickH = h;
    pickTex = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, pickTex);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, w, h, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
    // NEAREST throughout: these bytes are an integer, and any filtering would
    // blend two ids into a third that names nothing.
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    pickFb = gl.createFramebuffer();
    gl.bindFramebuffer(gl.FRAMEBUFFER, pickFb);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, pickTex, 0);
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    gl.bindTexture(gl.TEXTURE_2D, null);
  };
  let pickBlock = new Uint8Array((2 * SCAN_RADIUS + 1) ** 2 * 4);

  // Post-processing runs over a full-screen quad: two triangles covering clip
  // space, with the fragment shader doing the actual work per pixel.
  const quadBuf = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, quadBuf);
  gl.bufferData(
    gl.ARRAY_BUFFER,
    new Float32Array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1]),
    gl.STATIC_DRAW,
  );

  const postVertex = `attribute vec2 p; varying vec2 uv;
void main(){ uv=p*.5+.5; gl_Position=vec4(p,0.,1.); }`;

  // Keep what is brighter than the threshold. The knee is not decoration: with
  // a hard cutoff a travelling pulse crosses the threshold abruptly, so the
  // glow blinks on and off instead of swelling.
  const brightFragment = `precision mediump float; uniform sampler2D src;
uniform float threshold; uniform float knee; varying vec2 uv;
void main(){ vec4 c=texture2D(src,uv);
 float y=dot(c.rgb,vec3(.2126,.7152,.0722));
 float w=smoothstep(threshold-knee,threshold+knee,y);
 gl_FragColor=vec4(c.rgb*w,1.); }`;

  // One axis at a time. A true 2D blur has every pixel read a whole
  // neighbourhood; separating it into horizontal then vertical is visually
  // identical for a fraction of the work, which is why every bloom
  // implementation ping-pongs between two textures.
  const blurFragment = `precision mediump float; uniform sampler2D src;
uniform vec2 step; varying vec2 uv;
void main(){
 float w[9];
 w[0]=.0162; w[1]=.0540; w[2]=.1216; w[3]=.1946; w[4]=.2270;
 w[5]=.1946; w[6]=.1216; w[7]=.0540; w[8]=.0162;
 vec3 sum=vec3(0.);
 for(int i=0;i<9;i++){ sum+=texture2D(src,uv+step*float(i-4)).rgb*w[i]; }
 gl_FragColor=vec4(sum,1.); }`;

  const compositeFragment = `precision mediump float;
uniform sampler2D scene; uniform sampler2D bloom; uniform float intensity;
varying vec2 uv;
void main(){ vec4 s=texture2D(scene,uv); vec3 b=texture2D(bloom,uv).rgb;
 // Added, not mixed: bloom is light arriving on top of the scene, so it
 // brightens without washing out what is already there.
 vec3 rgb=s.rgb+b*intensity;
 // Premultiplied output requires alpha to cover every colour channel.
 float a=max(s.a,max(rgb.r,max(rgb.g,rgb.b)));
 gl_FragColor=vec4(rgb,a); }`;

  type Target = { fb: WebGLFramebuffer | null; tex: WebGLTexture | null; w: number; h: number };
  const makeTarget = (w: number, h: number): Target => {
    const tex = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, w, h, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
    // LINEAR so the downsampled bloom upsamples smoothly; NEAREST would band.
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    const fb = gl.createFramebuffer();
    gl.bindFramebuffer(gl.FRAMEBUFFER, fb);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0);
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    gl.bindTexture(gl.TEXTURE_2D, null);
    return { fb, tex, w, h };
  };
  const dropTarget = (t: Target | null) => {
    if (!t) return;
    if (t.tex) gl.deleteTexture(t.tex);
    if (t.fb) gl.deleteFramebuffer(t.fb);
  };

  let sceneTarget: Target | null = null;
  let bloomA: Target | null = null;
  let bloomB: Target | null = null;
  const bloomTargets = () => {
    const w = Math.max(1, gl.drawingBufferWidth);
    const h = Math.max(1, gl.drawingBufferHeight);
    if (sceneTarget && sceneTarget.w === w && sceneTarget.h === h) return;
    dropTarget(sceneTarget);
    dropTarget(bloomA);
    dropTarget(bloomB);
    const sw = Math.max(1, Math.floor(w / BLOOM_DOWNSAMPLE));
    const sh = Math.max(1, Math.floor(h / BLOOM_DOWNSAMPLE));
    sceneTarget = makeTarget(w, h);
    bloomA = makeTarget(sw, sh);
    bloomB = makeTarget(sw, sh);
  };

  let brightProgram: WebGLProgram | undefined;
  let blurProgram: WebGLProgram | undefined;
  let compositeProgram: WebGLProgram | undefined;
  const linkPost = (fragSrc: string) => {
    const prog = gl.createProgram()!;
    const vs = gl.createShader(gl.VERTEX_SHADER)!;
    gl.shaderSource(vs, postVertex);
    gl.compileShader(vs);
    const fs = gl.createShader(gl.FRAGMENT_SHADER)!;
    gl.shaderSource(fs, fragSrc);
    gl.compileShader(fs);
    gl.attachShader(prog, vs);
    gl.attachShader(prog, fs);
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
      // Shader linking is a runtime event, so this is the only place a
      // precision or naming mistake surfaces. Fail loudly rather than
      // rendering a blank map.
      console.error("bloom program link failed", gl.getProgramInfoLog(prog));
      return undefined;
    }
    return prog;
  };
  brightProgram = linkPost(brightFragment);
  blurProgram = linkPost(blurFragment);
  compositeProgram = linkPost(compositeFragment);

  const drawQuad = (prog: WebGLProgram) => {
    const loc = gl.getAttribLocation(prog, "p");
    gl.bindBuffer(gl.ARRAY_BUFFER, quadBuf);
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    gl.drawArrays(gl.TRIANGLES, 0, 6);
  };
  const bindTarget = (t: Target | null) => {
    gl.bindFramebuffer(gl.FRAMEBUFFER, t ? t.fb : null);
    gl.viewport(0, 0, t ? t.w : gl.drawingBufferWidth, t ? t.h : gl.drawingBufferHeight);
  };
  const setSampler = (prog: WebGLProgram, name: string, tex: WebGLTexture | null, unit: number) => {
    gl.activeTexture(gl.TEXTURE0 + unit);
    gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.uniform1i(gl.getUniformLocation(prog, name), unit);
  };

  /** Scene is already in sceneTarget; run the chain and composite to screen. */
  const postprocess = () => {
    if (!brightProgram || !blurProgram || !compositeProgram || !sceneTarget) return false;
    if (!bloomA || !bloomB) return false;
    const blendWas = gl.isEnabled(gl.BLEND);
    gl.disable(gl.BLEND);

    bindTarget(bloomA);
    gl.useProgram(brightProgram);
    setSampler(brightProgram, "src", sceneTarget.tex, 0);
    gl.uniform1f(gl.getUniformLocation(brightProgram, "threshold"), BLOOM_THRESHOLD);
    gl.uniform1f(gl.getUniformLocation(brightProgram, "knee"), BLOOM_KNEE);
    drawQuad(brightProgram);

    // Ping-pong: horizontal into B, vertical back into A, repeated. Spacing is
    // derived from sigma so the fixed 9-tap kernel covers the intended radius.
    const spread = BLOOM_SIGMA / BLOOM_DOWNSAMPLE / 3;
    gl.useProgram(blurProgram);
    for (let i = 0; i < BLOOM_PASSES; i++) {
      bindTarget(bloomB);
      setSampler(blurProgram, "src", bloomA.tex, 0);
      gl.uniform2f(gl.getUniformLocation(blurProgram, "step"), spread / bloomA.w, 0);
      drawQuad(blurProgram);
      bindTarget(bloomA);
      setSampler(blurProgram, "src", bloomB.tex, 0);
      gl.uniform2f(gl.getUniformLocation(blurProgram, "step"), 0, spread / bloomA.h);
      drawQuad(blurProgram);
    }

    bindTarget(null);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.useProgram(compositeProgram);
    setSampler(compositeProgram, "scene", sceneTarget.tex, 0);
    setSampler(compositeProgram, "bloom", bloomA.tex, 1);
    gl.uniform1f(gl.getUniformLocation(compositeProgram, "intensity"), BLOOM_INTENSITY);
    drawQuad(compositeProgram);

    if (blendWas) gl.enable(gl.BLEND);
    return true;
  };
  /** Index into renderedPoints under a CSS-pixel coordinate, or -1. */
  const pickAt = (cssX: number, cssY: number): number => {
    pickTarget();
    if (!pickFb) return -1;
    const ratio = pixelRatio();
    const px = Math.round(cssX * ratio);
    // readPixels counts from the bottom-left; DOM coordinates from the top.
    const py = Math.round(pickH - cssY * ratio);
    if (px < 0 || py < 0 || px >= pickW || py >= pickH) return -1;
    gl.bindFramebuffer(gl.FRAMEBUFFER, pickFb);
    pickPass = true;
    // Blending would average neighbouring ids into a meaningless third value.
    const blendWas = gl.isEnabled(gl.BLEND);
    gl.disable(gl.BLEND);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    // Same draw path, so pick geometry can never drift from what is on
    // screen; draw() skips the terrain/web/fog/junction passes while
    // pickPass is set, since only the points carry ids.
    draw(lastDrawTime);
    pickPass = false;
    if (blendWas) gl.enable(gl.BLEND);
    // Read a block, not a single pixel. One pixel answers "what is directly
    // under the cursor", but the scan this replaces answered "what is nearest
    // within 12px" — and with no depth test, a lone pixel resolves overlaps by
    // draw order instead of by distance. scripts/plot_picking.py measured that
    // divergence at 647 of 963 hits. Scanning the block for the nearest
    // painted pixel restores the original semantic; it is still one readback
    // and still independent of how many points exist.
    const r = Math.max(1, Math.round(SCAN_RADIUS * ratio));
    const x0 = Math.max(0, px - r);
    const y0 = Math.max(0, py - r);
    const x1 = Math.min(pickW, px + r + 1);
    const y1 = Math.min(pickH, py + r + 1);
    const w = x1 - x0;
    const h = y1 - y0;
    if (w <= 0 || h <= 0) {
      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
      return -1;
    }
    const need = w * h * 4;
    if (pickBlock.length < need) pickBlock = new Uint8Array(need);
    gl.readPixels(x0, y0, w, h, gl.RGBA, gl.UNSIGNED_BYTE, pickBlock);
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    let best = -1;
    let bestD = (r + 1) * (r + 1);
    for (let y = 0; y < h; y++) {
      const dy = y0 + y - py;
      for (let x = 0; x < w; x++) {
        const o = (y * w + x) * 4;
        const id = pickBlock[o]! + (pickBlock[o + 1]! << 8) + (pickBlock[o + 2]! << 16);
        if (id === 0) continue;
        const dx = x0 + x - px;
        const d = dx * dx + dy * dy;
        if (d < bestD) {
          bestD = d;
          best = id - 1;
        }
      }
    }
    return best;
  };
  let lastFrame = 0;
  // Every eased value in render() decays toward an explicit target, so "is
  // anything still moving" is decidable and the loop can park itself (#101).
  //
  // The one animation that never settles is the focus pulse in the point
  // shader — step(1.5, level + focusT), where level is 1 only outside the
  // content view with a domain or subtopic focused. At overview the gate is
  // 1.0 and never fires, which is exactly the resting state that was burning
  // a core repainting identical frames. While focused the pulse is a
  // deliberate visual, so the loop has to stay awake or it would freeze
  // mid-breath.
  const settled = (a: number, b: number) => Math.abs(a - b) <= 1e-3;
  const animating = () => {
    if (geometryDirty || labelsDirty) return true;
    if (drag || flyItem || zoomAnchor) return true;
    if (introT < 1 || focusT < 1) return true;
    if (momentum.vx || momentum.vy) return true;
    if (!settled(scale, scaleTarget)) return true;
    if (!settled(morph, morphTarget)) return true;
    if (!settled(dimVal, dimTarget)) return true;
    if (!settled(reliefT, reliefTarget)) return true;
    if (!settled(fogT, fogOn ? 1 : 0)) return true;
    if (!settled(shellT, fogShell ? 1 : 0)) return true;
    if (!settled(webT, webOn ? 1 : 0)) return true;
    if (!settled(terrainT, terrainOn ? 1 : 0)) return true;
    if (!settled(subColorT, view === "all" && focus.dom !== undefined ? 1 : 0)) return true;
    // Flow pulses travel on a live clock (#107 feature A), so the web being
    // visible is itself a reason to keep drawing — without this the loop parks
    // the moment everything else settles and the pulse freezes mid-travel,
    // which reads as a rendering bug rather than a missing feature. Reduced
    // motion pins the clock, so there the loop is free to park.
    if (!reduceMotion && webT > 0.01 && dimVal > 0.01) return true;
    return view !== "content" && focusLevel(focus) !== "overview";
  };
  // Restart a parked loop. lastFrame resets so the first frame back uses the
  // nominal dt instead of the whole idle gap, which would jump every easing
  // straight to its target.
  const wake = () => {
    if (frame) return;
    lastFrame = 0;
    frame = requestAnimationFrame(render);
  };
  const render = (now = 0) => {
    const dt = lastFrame ? Math.min(0.05, (now - lastFrame) / 1000) : 0.016;
    lastFrame = now;
    const dm2 = morphTarget - morph;
    morph = Math.abs(dm2) <= 1e-3 ? morphTarget : morph + dm2 * (1 - Math.exp(-5 * dt));
    const dd = dimTarget - dimVal;
    dimVal = Math.abs(dd) <= 1e-3 ? dimTarget : dimVal + dd * (1 - Math.exp(-5 * dt));
    const dr = reliefTarget - reliefT;
    reliefT = Math.abs(dr) <= 1e-3 ? reliefTarget : reliefT + dr * (1 - Math.exp(-5 * dt));
    // wheel glide: ease scale to its target, holding the anchor point fixed
    if (!flyItem && zoomAnchor && Math.abs(scaleTarget - scale) > 1e-3) {
      const previous = scale;
      scale += (scaleTarget - scale) * (1 - Math.exp(-10 * dt));
      const ratio = scale / previous;
      offset = [
        zoomAnchor[0] - (zoomAnchor[0] - offset[0]) * ratio,
        zoomAnchor[1] - (zoomAnchor[1] - offset[1]) * ratio,
      ];
    } else if (zoomAnchor && Math.abs(scaleTarget - scale) <= 1e-3) {
      scale = scaleTarget;
      zoomAnchor = null;
    }
    // pan coast: integrate momentum with exponential decay to a soft stop
    if (!drag && (momentum.vx || momentum.vy)) {
      offset = [offset[0] + momentum.vx * dt, offset[1] + momentum.vy * dt];
      momentum = { vx: decay(momentum.vx, dt), vy: decay(momentum.vy, dt) };
      if (Math.hypot(momentum.vx, momentum.vy) < 0.005) killMomentum();
    }
    focusT = Math.min(1, focusT + dt / 0.9);
    introT = Math.min(1, introT + dt / 1.5);
    if (introT >= 1 && canvas.dataset.intro) delete canvas.dataset.intro;
    const subColorTarget = view === "all" && focus.dom !== undefined ? 1 : 0;
    const ds = subColorTarget - subColorT;
    subColorT = Math.abs(ds) <= 1e-3 ? subColorTarget : subColorT + ds * (1 - Math.exp(-4 * dt));
    const fogTarget = fogOn ? 1 : 0;
    const dfg = fogTarget - fogT;
    fogT = Math.abs(dfg) <= 1e-3 ? fogTarget : fogT + dfg * (1 - Math.exp(-4 * dt));
    const shellTarget = fogShell ? 1 : 0;
    const dsh = shellTarget - shellT;
    shellT = Math.abs(dsh) <= 1e-3 ? shellTarget : shellT + dsh * (1 - Math.exp(-4 * dt));
    const webTarget = webOn ? 1 : 0;
    const dwb = webTarget - webT;
    webT = Math.abs(dwb) <= 1e-3 ? webTarget : webT + dwb * (1 - Math.exp(-4 * dt));
    const terrainTarget = terrainOn ? 1 : 0;
    const dte = terrainTarget - terrainT;
    terrainT = Math.abs(dte) <= 1e-3 ? terrainTarget : terrainT + dte * (1 - Math.exp(-4 * dt));
    if (flyItem) {
      const e = 1 - Math.exp(-8 * dt);
      scale += (scaleTarget - scale) * e;
      const [sx, sy] = project(worldOf(flyItem));
      const ox = offset[0] - ((2 * sx) / canvas.clientWidth - 1);
      const oy = offset[1] + ((2 * sy) / canvas.clientHeight - 1);
      offset = [offset[0] + (ox - offset[0]) * e, offset[1] + (oy - offset[1]) * e];
      if (
        Math.abs(scaleTarget - scale) < 1e-3 &&
        Math.abs(ox - offset[0]) < 1e-3 &&
        Math.abs(oy - offset[1]) < 1e-3
      ) {
        scale = scaleTarget;
        flyItem = undefined;
      }
    }
    // Bloom (#107 C): the scene goes into a texture first, then the post chain
    // composites it to the screen. If any post program failed to link the
    // scene is drawn straight to the canvas instead, so a shader problem
    // degrades to "no glow" rather than to a blank map.
    bloomTargets();
    const post =
      !bloomOff && Boolean(brightProgram && blurProgram && compositeProgram && sceneTarget);
    if (post) bindTarget(sceneTarget);
    draw(now * 0.001);
    if (post) postprocess();
    placeLabels();
    placeRoad();
    frame = animating() ? requestAnimationFrame(render) : 0;
  };
  const placeLabels = () => {
    if (!labels) return;
    if (labelsDirty) {
      // Hierarchy-aware label sets: content themes; all-view domains at
      // overview; a focused domain's subtopics; the focused subtopic alone.
      const contentView = view === "content";
      const entries = contentView
        ? data.content.groups
            .map((group, key) => ({
              key,
              label: group.label,
              n: group.n,
              focus: { dom: key } as MapFocus,
            }))
            .filter((entry) => focus.dom === undefined || focus.dom === entry.key)
        : focus.dom === undefined
          ? data.all.domains
              .map((domain, key) => ({
                key,
                label: domain.label,
                n: domain.n,
                focus: { dom: key } as MapFocus,
              }))
              .filter((entry) => !hiddenDoms.has(entry.key))
          : data.all.groups
              .map((group, key) => ({
                key,
                label: group.label,
                n: group.n,
                focus: { dom: group.domain ?? -1, sub: key } as MapFocus,
              }))
              .filter(
                (entry) =>
                  entry.focus.dom === focus.dom &&
                  (focus.sub === undefined || focus.sub === entry.key),
              );
      const groupOf =
        !contentView && focus.dom === undefined
          ? (item: RenderedPoint) => item.domain
          : (item: RenderedPoint) => item.group;
      const buckets = new Map<
        number,
        { x: number; y: number; z: number; fx: number; fy: number; n: number; points: number[][] }
      >();
      for (const entry of entries)
        buckets.set(entry.key, { x: 0, y: 0, z: 0, fx: 0, fy: 0, n: 0, points: [] });
      for (const item of renderedPoints) {
        const bucket = buckets.get(groupOf(item));
        if (!bucket) continue;
        const s3 = contentView ? item.p3b : item.p3a;
        const s2 = contentView ? item.p2b : item.p2a;
        bucket.x += s3[0];
        bucket.y += s3[1];
        bucket.z += s3[2];
        bucket.fx += s2[0];
        bucket.fy += s2[1];
        bucket.n++;
        bucket.points.push(s3);
      }
      labels.replaceChildren();
      leaders?.replaceChildren();
      // the road group survives label rebuilds — it is owned by setRoute
      if (roadGroup) leaders?.appendChild(roadGroup);
      const single = contentView ? focus.dom !== undefined : focus.sub !== undefined;
      labelItems = entries
        .filter((entry) => entry.n && buckets.get(entry.key)!.n)
        .sort((a, b) => b.n - a.n)
        .slice(0, single ? 1 : 10)
        .map((entry, rank) => {
          const bucket = buckets.get(entry.key)!;
          const c3 = [bucket.x / bucket.n, bucket.y / bucket.n, bucket.z / bucket.n];
          const c2 = [bucket.fx / bucket.n, bucket.fy / bucket.n];
          const radius = Math.sqrt(
            Math.max(
              0,
              ...bucket.points.map(
                (point) =>
                  (point[0] - c3[0]) ** 2 + (point[1] - c3[1]) ** 2 + (point[2] - c3[2]) ** 2,
              ),
            ),
          );
          const node = document.createElement("div");
          node.className = "map-label";
          node.textContent = entry.label;
          node.style.fontSize = `${Math.max(10, Math.min(14, 9 + Math.sqrt(entry.n) * 0.25))}px`;
          node.style.pointerEvents = "auto";
          node.style.cursor = "pointer";
          node.onclick = () => {
            onFocus?.(entry.focus);
          };
          labels.appendChild(node);
          const line = leaders
            ? document.createElementNS("http://www.w3.org/2000/svg", "line")
            : undefined;
          if (line) {
            line.setAttribute("stroke-width", "1");
            leaders!.appendChild(line);
          }
          return { c3, c2, radius, node, line, rank, n: entry.n };
        });
      labelsDirty = false;
    }
    const placed: Array<{ x: number; y: number; width: number }> = [];
    for (const item of labelItems) {
      const [x, centerY, depth] = project(blend(item.c3, item.c2));
      const spread = (item.radius * scale * canvas.clientHeight * 0.25) / depth;
      let y = centerY - spread - 22;
      const width =
        (item.node.textContent?.length ?? 1) * parseFloat(item.node.style.fontSize) * 0.72;
      for (
        let i = 0;
        i < 10 &&
        placed.some(
          (other) =>
            Math.abs(other.y - y) < 22 && Math.abs(other.x - x) < (other.width + width) / 2 + 10,
        );
        i++
      )
        y -= 22;
      const visible =
        depth > 0 &&
        x >= 0 &&
        y >= 40 &&
        x <= canvas.clientWidth - (legendOpen ? 290 : 70) &&
        y <= canvas.clientHeight &&
        !(item.rank >= 6 && spread < 70);
      item.node.style.display = visible ? "block" : "none";
      if (item.line) item.line.style.display = "none";
      if (!visible) continue;
      y = Math.max(46, y);
      const size = parseFloat(item.node.style.fontSize);
      item.node.style.left = `${x}px`;
      item.node.style.top = `${y}px`;
      const alpha = item.rank < 6 ? 0.9 : Math.min(0.9, (spread - 70) / 120 + 0.35);
      item.node.style.opacity = `${alpha}`;
      const gap = centerY - y - size;
      if (item.line && gap > 14) {
        item.line.style.display = "block";
        item.line.setAttribute("stroke", `rgba(255,255,255,${(0.16 * alpha).toFixed(3)})`);
        item.line.setAttribute("x1", `${x}`);
        item.line.setAttribute("y1", `${centerY - Math.min(spread * 0.7, gap - 6)}`);
        item.line.setAttribute("x2", `${x}`);
        item.line.setAttribute("y2", `${y + size * 0.8}`);
      }
      placed.push({ x, y, width });
    }
  };
  const SVG_NS = "http://www.w3.org/2000/svg";
  const buildRoad = () => {
    if (!leaders) return;
    if (!roadGroup) {
      roadGroup = document.createElementNS(SVG_NS, "g");
      roadPath = document.createElementNS(SVG_NS, "path");
      roadPath.setAttribute("fill", "none");
      roadPath.setAttribute("stroke", "rgba(217,164,65,0.55)");
      roadPath.setAttribute("stroke-width", "1.5");
      roadPath.setAttribute("stroke-dasharray", "6 5");
      roadGroup.appendChild(roadPath);
      leaders.appendChild(roadGroup);
    }
    for (const dot of roadDots) dot.remove();
    roadDots = [];
    roadPath?.setAttribute("d", "");
    roadGroup.style.display = route ? "" : "none";
    if (!route) return;
    for (const waypoint of route) {
      const dot = document.createElementNS(SVG_NS, "circle");
      const endpoint = waypoint.kind !== "stop";
      dot.setAttribute("r", endpoint ? "5" : "3.5");
      dot.setAttribute("fill", endpoint ? "#f0eee7" : "#d9a441");
      dot.setAttribute("stroke", "rgba(0,0,0,0.6)");
      dot.setAttribute("stroke-width", "1");
      dot.style.pointerEvents = "auto";
      dot.style.cursor = "pointer";
      const title = document.createElementNS(SVG_NS, "title");
      title.textContent = waypoint.title;
      dot.appendChild(title);
      dot.addEventListener("click", () => {
        const item = renderedPoints[waypoint.index];
        if (item) flyTo(item.point);
        wake();
      });
      roadGroup.appendChild(dot);
      roadDots.push(dot);
    }
  };
  const placeRoad = () => {
    if (!roadGroup || !route) return;
    let d = "";
    route.forEach((waypoint, k) => {
      const item = renderedPoints[waypoint.index];
      const dot = roadDots[k];
      if (!item) {
        if (dot) dot.style.display = "none";
        return;
      }
      const [x, y] = project(worldOf(item));
      d += `${d ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`;
      if (dot) {
        dot.setAttribute("cx", x.toFixed(1));
        dot.setAttribute("cy", y.toFixed(1));
        dot.style.display = "";
      }
    });
    roadPath?.setAttribute("d", d);
  };
  const pick = (event: MouseEvent) => {
    if (drag) return;
    const rect = canvas.getBoundingClientRect();
    if (
      event.clientX < rect.left ||
      event.clientX > rect.right ||
      event.clientY < rect.top ||
      event.clientY > rect.bottom
    ) {
      hoveredPoint = undefined;
      onHover?.();
      return;
    }
    // One pixel read replaces projecting every point (#101 fix 2). The
    // visibility rules the old scan applied by hand — signalOnly, and focus
    // attenuation under 0.2 — are enforced in the pick fragment shader by
    // discarding on the alpha it already computes, so hovering can never
    // catch something the eye cannot see.
    const index = pickAt(event.clientX - rect.left, event.clientY - rect.top);
    const hit = index >= 0 ? renderedPoints[index] : undefined;
    hoveredPoint = hit?.point;
    onHover?.(hit ? { point: hit.point, x: event.clientX, y: event.clientY } : undefined);
  };
  const down = (event: MouseEvent) => {
    if (event.button !== 0 && event.button !== 2) return;
    event.preventDefault();
    moved = 0;
    orbit = (dimTarget === 1 || reliefTarget === 1) && event.button === 0 && !event.shiftKey;
    drag = { x: event.clientX, y: event.clientY };
    canvas.classList.add("dragging");
    killMomentum();
    samples = [{ x: event.clientX, y: event.clientY, t: performance.now() }];
  };
  const move = (event: MouseEvent) => {
    if (!drag) {
      pick(event);
      return;
    }
    const dx = event.clientX - drag.x;
    const dy = event.clientY - drag.y;
    moved += Math.abs(dx) + Math.abs(dy);
    flyItem = undefined;
    scaleTarget = scale;
    momentum = { vx: 0, vy: 0 };
    if (orbit) {
      angle -= dx * 0.005;
      tilt = Math.max(-1.35, Math.min(1.35, tilt + dy * 0.005));
    } else {
      offset = [offset[0] + (dx / innerWidth) * 2, offset[1] - (dy / innerHeight) * 2];
      pushSample(samples, { x: event.clientX, y: event.clientY, t: performance.now() });
    }
    drag = { x: event.clientX, y: event.clientY };
    onHover?.();
  };
  const up = () => {
    if (drag && !orbit && !reduceMotion) {
      const v = releaseVelocity(samples); // px/ms in screen space
      // convert to NDC offset units/second: offset spans 2 across the viewport
      momentum = { vx: (v.vx * 1000 * 2) / innerWidth, vy: (-v.vy * 1000 * 2) / innerHeight };
      if (Math.hypot(momentum.vx, momentum.vy) < 0.02) killMomentum();
    }
    samples = [];
    drag = undefined;
    orbit = false;
    canvas.classList.remove("dragging");
  };
  // exact cursor-anchored zoom: screen = world*k*scale + pan, so holding the
  // cursor's NDC point fixed means pan' = c - (c - pan) * (scale'/scale)
  let zoomAnchor: [number, number] | null = null;
  const wheel = (event: WheelEvent) => {
    event.preventDefault();
    flyItem = undefined;
    killMomentum();
    const rect = canvas.getBoundingClientRect();
    zoomAnchor = [
      ((event.clientX - rect.left) / rect.width) * 2 - 1,
      1 - ((event.clientY - rect.top) / rect.height) * 2,
    ];
    scaleTarget = Math.max(
      0.3,
      Math.min(12, (scaleTarget || scale) * Math.exp(-event.deltaY * 0.0012)),
    );
    if (reduceMotion) {
      const ratio = scaleTarget / scale;
      scale = scaleTarget;
      offset = [
        zoomAnchor[0] - (zoomAnchor[0] - offset[0]) * ratio,
        zoomAnchor[1] - (zoomAnchor[1] - offset[1]) * ratio,
      ];
      zoomAnchor = null;
    }
  };
  const contextmenu = (event: MouseEvent) => event.preventDefault();
  const open = () => {
    if (hoveredPoint?.u) window.open(hoveredPoint.u, "_blank", "noopener");
  };
  const flyTo = (point: MapPoint) => {
    const item = renderedPoints.find((entry) => entry.point === point);
    if (item) {
      scaleTarget = Math.max(scale, 1.8);
      flyItem = item;
      killMomentum();
    }
  };
  // Drill-down: overview click focuses the point's domain; a second click
  // inside a focused domain focuses its subtopic (noise keeps domain focus);
  // clicking at subtopic depth or on empty space pops one level. The route
  // owns the focus state — the renderer only reports via onFocus.
  const click = () => {
    if (moved >= 4) return;
    if (roadPick) {
      if (hoveredPoint) roadPick(hoveredPoint);
      return;
    }
    if (!hoveredPoint) {
      flyItem = undefined;
      scaleTarget = scale;
      onFocus?.(focus.sub !== undefined ? { dom: focus.dom } : {});
      return;
    }
    if (view === "content") {
      const th = hoveredPoint.th ?? -1;
      if (th < 0) return;
      flyTo(hoveredPoint);
      onFocus?.({ dom: th });
      return;
    }
    if (focus.dom === undefined) {
      onFocus?.({ dom: hoveredPoint.dom });
      return;
    }
    if (focus.sub === undefined) {
      const sub = hoveredPoint.g >= 0 ? hoveredPoint.g : undefined;
      if (sub !== undefined) flyTo(hoveredPoint);
      onFocus?.({ dom: focus.dom, sub });
      return;
    }
    onFocus?.({ dom: focus.dom });
  };
  resize();
  // Every input path must wake a parked loop (#101). Wrapped once here and
  // held in consts so destroy() unregisters these exact references rather
  // than the unwrapped originals. contextmenu only calls preventDefault, so
  // it changes no state and needs no wake.
  const onResize = () => {
    resize();
    wake();
  };
  const onDown = (event: MouseEvent) => {
    down(event);
    wake();
  };
  const onClick = () => {
    click();
    wake();
  };
  const onOpen = () => {
    open();
    wake();
  };
  const onMove = (event: MouseEvent) => {
    move(event);
    wake();
  };
  const onUp = () => {
    up();
    wake();
  };
  const onWheel = (event: WheelEvent) => {
    wheel(event);
    wake();
  };
  addEventListener("resize", onResize);
  canvas.addEventListener("mousedown", onDown);
  canvas.addEventListener("click", onClick);
  canvas.addEventListener("dblclick", onOpen);
  canvas.addEventListener("contextmenu", contextmenu);
  addEventListener("mousemove", onMove);
  addEventListener("mouseup", onUp);
  canvas.addEventListener("wheel", onWheel, { passive: false });
  render();
  return {
    setView: (next) => {
      view = next;
      morphTarget = next === "content" ? 1 : 0;
      focus = {};
      hover = undefined;
      hiddenDoms.clear();
      flyItem = undefined;
      scaleTarget = scale;
      killMomentum();
      zoomAnchor = null;
      retarget();
      geometryDirty = true;
      labelsDirty = true;
      wake();
    },
    setDimension: (next) => {
      requestedDim = next ? 0 : 1;
      retargetDims();
      flyItem = undefined;
      scaleTarget = scale;
      killMomentum();
      zoomAnchor = null;
      wake();
    },
    setClock: (next) => {
      // A uniform change only — the buffer is untouched, so this does not
      // set geometryDirty. wake() is enough because the scrubber is manual:
      // each drag paints a frame and the loop parks again. Nothing here
      // animates on its own, so animating() needs no new clause.
      clock = next;
      wake();
    },
    setFilters: (signal, recent, media = false) => {
      signalOnly = signal;
      recentOnly = recent;
      mediaOnly = media;
      geometryDirty = true;
      wake();
    },
    setFocus: (next) => {
      focus = next;
      retarget();
      labelsDirty = true;
      wake();
    },
    setHover: (next) => {
      hover = next;
      retarget();
      wake();
    },
    setHiddenDomains: (doms) => {
      hiddenDoms = new Set(doms);
      retarget();
      labelsDirty = true;
      wake();
    },
    // legendOpen and fogLevel feed the shaders directly rather than easing
    // toward a target, so animating() stays false for them. Waking still
    // paints exactly one frame and parks again, which is what they need.
    setLegendOpen: (open) => {
      legendOpen = open;
      wake();
    },
    setTerrain: (next) => {
      terrainOn = next;
      retargetDims();
      wake();
    },
    setWeb: (next) => {
      webOn = next;
      wake();
    },
    setFog: (next) => {
      fogOn = next;
      wake();
    },
    setFogLevel: (next) => {
      fogLevel = next;
      wake();
    },
    setFogShell: (next) => {
      fogShell = next;
      wake();
    },
    setRoadPick: (cb) => {
      roadPick = cb;
    },
    setRoute: (next) => {
      route = next && next.length >= 2 ? next : undefined;
      buildRoad();
      wake();
    },
    flyTo: (point) => {
      flyTo(point);
      wake();
    },
    destroy: () => {
      cancelAnimationFrame(frame);
      frame = 0;
      removeEventListener("resize", onResize);
      canvas.removeEventListener("mousedown", onDown);
      canvas.removeEventListener("click", onClick);
      canvas.removeEventListener("dblclick", onOpen);
      canvas.removeEventListener("contextmenu", contextmenu);
      removeEventListener("mousemove", onMove);
      removeEventListener("mouseup", onUp);
      canvas.removeEventListener("wheel", onWheel);
      delete canvas.dataset.intro;
      labels?.replaceChildren();
      leaders?.replaceChildren();
      gl.deleteBuffer(buffer);
      if (pickTex) gl.deleteTexture(pickTex);
      if (pickFb) gl.deleteFramebuffer(pickFb);
      if (quadBuf) gl.deleteBuffer(quadBuf);
      dropTarget(sceneTarget);
      dropTarget(bloomA);
      dropTarget(bloomB);
      if (brightProgram) gl.deleteProgram(brightProgram);
      if (blurProgram) gl.deleteProgram(blurProgram);
      if (compositeProgram) gl.deleteProgram(compositeProgram);
      for (const bufs of Object.values(terrainBuffers)) {
        gl.deleteBuffer(bufs.contours);
        gl.deleteBuffer(bufs.ridges);
      }
      if (lineProgram) gl.deleteProgram(lineProgram);
      for (const bufs of Object.values(webBuffers)) gl.deleteBuffer(bufs.buf);
      if (webProgram) gl.deleteProgram(webProgram);
      for (const bufs of Object.values(junctionBuffers)) gl.deleteBuffer(bufs.buf);
      if (junctionProgram) gl.deleteProgram(junctionProgram);
      for (const bufs of Object.values(fogBuffers)) gl.deleteBuffer(bufs.buf);
      if (fogProgram) gl.deleteProgram(fogProgram);
      gl.deleteProgram(program);
      killMomentum();
    },
  };
}
