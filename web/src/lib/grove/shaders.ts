// Shared grove shader sources. All palette, glow, pulse, and x-ray channels
// here are decorative; measured topology/mass only arrive through geometry.
const RAMP = `float ramp(float p){ return .5 - .5*cos(clamp(p,0.,1.)*3.14159265); }`

const WIND = `vec3 windSway(vec3 wp, float d, float t, float amp){
  float ph = wp.x*1.3 + wp.z*2.1 + wp.y*.6;
  float s = .55*sin(t*1.15 + ph) + .3*sin(t*2.4 + ph*1.7) + .15*sin(t*4.1 + ph*.9);
  return vec3(s, .25*sin(t*.9 + ph*1.3), s*.7) * amp * d*d; }`

export const PALETTE_GLSL = `
const float TAU = 6.2831853;
uniform vec3 uPaletteA; uniform vec3 uPaletteB; uniform vec3 uPaletteC; uniform vec3 uPaletteD;
uniform float uPaletteOffset; uniform float uPalettePhase;
uniform float uPaletteTravel; uniform float uPaletteMotion; uniform float uPaletteStrength;
vec3 cosinePalette(float t, vec3 a, vec3 b, vec3 c, vec3 d) {
  return a + b * cos(TAU * (c * t + d));
}
vec3 topicColor(float depth, float time) {
  float t = uPaletteOffset + depth*uPaletteTravel + sin(time*.35 + uPalettePhase*TAU)*uPaletteMotion;
  return clamp(cosinePalette(t, uPaletteA, uPaletteB, uPaletteC, uPaletteD), 0., 1.);
}
vec3 rootColor(vec3 c, float root) {
  float luma = dot(c, vec3(.2126,.7152,.0722));
  return mix(c, mix(vec3(luma), c, .55)*.58, root);
}`

export const tubeVertex = `attribute vec3 roff; attribute float depth;
uniform float uProgress; uniform float uTime; uniform float uWind;
varying float vDepth; varying float vGrow; varying vec3 vN; varying vec3 vView;
${RAMP}
${WIND}
void main(){
  float g = ramp(uProgress*1.35 - depth);
  vec3 p = position + roff*g;
  p += windSway(position, depth, uTime, uWind*.09);
  vDepth = depth; vGrow = g;
  vec4 mv = modelViewMatrix*vec4(p,1.);
  vN = normalMatrix*normalize(roff + vec3(1e-5));
  vView = -mv.xyz;
  gl_Position = projectionMatrix*mv; }`

export const tubeFragment = `precision highp float;
uniform float uTime; uniform float uRoot;
varying float vDepth; varying float vGrow; varying vec3 vN; varying vec3 vView;
${PALETTE_GLSL}
void main(){
  if (vGrow < .03) discard;
  vec3 n = normalize(vN); vec3 v = normalize(vView);
  float facing = abs(dot(n, v));
  float fres = pow(1. - facing, 2.2);
  vec3 family = rootColor(topicColor(vDepth, uTime), uRoot);
  vec3 bark = mix(vec3(.13,.115,.09), family, uPaletteStrength*.25);
  vec3 rim = mix(vec3(.42,.48,.43), family, uPaletteStrength);
  vec3 c = bark*(.28 + .34*facing) + rim*fres*.9;
  gl_FragColor = vec4(c, 1.); }`

export const xrayTubeFragment = `precision highp float;
uniform float uTime; uniform float uRoot; uniform float uWireGlow; uniform float uWireBody;
varying float vDepth; varying float vGrow; varying vec3 vN; varying vec3 vView;
${PALETTE_GLSL}
void main(){
  if (vGrow < .03) discard;
  vec3 n = normalize(vN); vec3 v = normalize(vView);
  float facing = abs(dot(n, v));
  float halo = pow(1. - facing, 1.35);
  vec3 family = rootColor(mix(vec3(.38,.5,.48), topicColor(vDepth, uTime), uPaletteStrength), uRoot);
  float rootDim = mix(1., .62, uRoot);
  float a = vGrow*rootDim*(uWireBody*(.12 + .16*facing) + uWireGlow*.34*halo);
  gl_FragColor = vec4(family, clamp(a, 0., .72)); }`

export const lineVertex = `attribute float depth;
uniform float uProgress; uniform float uTime; uniform float uWind;
varying float vDepth; varying float vGrow;
${RAMP}
${WIND}
void main(){
  vDepth = depth; vGrow = ramp(uProgress*1.35 - depth);
  vec3 p = position + windSway(position, depth, uTime, uWind*.09);
  gl_Position = projectionMatrix*modelViewMatrix*vec4(p,1.); }`

export const xrayLineFragment = `precision highp float;
uniform float uTime; uniform float uRoot; uniform float uWireGlow; uniform float uWirePulse;
varying float vDepth; varying float vGrow;
${PALETTE_GLSL}
void main(){
  float pulse = .5 + .5*sin(uTime*1.15 - vDepth*9.);
  float energy = .42 + uWirePulse*.58*pulse;
  float rootDim = mix(1., .58, uRoot);
  float a = vGrow*rootDim*uWireGlow*energy;
  vec3 family = rootColor(mix(vec3(.38,.5,.48), topicColor(vDepth, uTime), uPaletteStrength), uRoot);
  gl_FragColor = vec4(family, clamp(a, 0., 1.)); }`

export const leafVertex = `attribute float iDepth; attribute float iPhase;
uniform float uProgress; uniform float uTime; uniform float uWind;
varying vec3 vN; varying vec3 vView; varying float vPhase; varying float vAlong; varying float vDepth;
${RAMP}
${WIND}
void main(){
  float g = ramp(uProgress*1.35 - iDepth);
  float along = uv.y;
  float sway = along*along*(.5*sin(uTime*1.9 + iPhase*6.28) + .3*sin(uTime*3.7 + iPhase*9.4) + .2*sin(uTime*.7 + iPhase*3.1))*.08;
  vec3 p = position*g;
  p.x += sway; p.z += sway*.6;
  vec4 wp = instanceMatrix*vec4(p,1.);
  vN = normalMatrix*mat3(instanceMatrix)*normal;
  wp.xyz += windSway(wp.xyz, iDepth, uTime, uWind*.09);
  vec4 world = modelViewMatrix*wp;
  vView = -world.xyz; vPhase = iPhase; vAlong = along; vDepth = iDepth;
  gl_Position = projectionMatrix*world; }`

export const leafFragment = `precision highp float;
uniform float uTime;
varying vec3 vN; varying vec3 vView; varying float vPhase; varying float vAlong; varying float vDepth;
${PALETTE_GLSL}
void main(){
  vec3 n = normalize(vN); vec3 v = normalize(vView);
  float facing = abs(dot(n, v));
  float fres = pow(1. - facing, 2.);
  vec3 family = topicColor(vDepth, uTime);
  vec3 bright = topicColor(vDepth + .18 + vPhase*.06, uTime);
  vec3 botanical = vec3(.14,.24,.13);
  vec3 base = mix(botanical, mix(family, bright, vPhase*vPhase*.35), uPaletteStrength);
  base *= .58 + .42*vAlong;
  vec3 c = base*(.34 + .54*facing) + family*fres*.42*uPaletteStrength;
  gl_FragColor = vec4(c, 1.); }`
