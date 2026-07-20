import { Effect } from "postprocessing";
import { Uniform } from "three";

/* Static, seeded film grain: hash of the fragment coordinate, no time
   uniform. Deterministic by design — grove/growth replays must reproduce
   pixel-for-pixel, so the grain must never animate. */
const fragment = /* glsl */ `
uniform float intensity;

float hash21(vec2 p) {
  p = fract(p * vec2(123.34, 456.21));
  p += dot(p, p + 45.32);
  return fract(p.x * p.y);
}

void mainImage(const in vec4 inputColor, const in vec2 uv, out vec4 outputColor) {
  float g = hash21(gl_FragCoord.xy) - 0.5;
  outputColor = vec4(inputColor.rgb + g * intensity, inputColor.a);
}
`;

export class SeededGrainEffect extends Effect {
  constructor(intensity = 0.05) {
    super("SeededGrainEffect", fragment, {
      uniforms: new Map([["intensity", new Uniform(intensity)]]),
    });
  }
}
