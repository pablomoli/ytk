import{A as e,B as t,D as n,E as r,F as i,H as a,M as o,P as s,S as c,g as l,o as u,p as d,u as f,v as p}from"./index-Ccb-21M1.js";var m=`
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = vec4(position.xy, 0.0, 1.0);
}`,h=`
precision highp float;
varying vec2 vUv;
uniform sampler2D uState;
uniform vec2 uTexel;
uniform vec2 uFrom;
uniform vec2 uTo;
uniform float uRadius;
uniform float uProgress;
uniform float uSeed;
uniform float uActive;
uniform float uCopy;

float hash21(vec2 p) {
  p = fract(p * vec2(123.34, 456.21));
  p += dot(p, p + 45.32);
  return fract(p.x * p.y);
}

float noise(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash21(i), hash21(i + vec2(1.0, 0.0)), f.x),
             mix(hash21(i + vec2(0.0, 1.0)), hash21(i + vec2(1.0)), f.x), f.y);
}

float segmentDistance(vec2 p, vec2 a, vec2 b) {
  vec2 pa = p - a;
  vec2 ba = b - a;
  float h = clamp(dot(pa, ba) / max(dot(ba, ba), 0.00001), 0.0, 1.0);
  return length(pa - ba * h);
}

void main() {
  vec4 state = texture2D(uState, vUv);
  if (uCopy > 0.5) {
    gl_FragColor = state;
    return;
  }

  vec4 north = texture2D(uState, vUv + vec2(0.0, uTexel.y));
  vec4 south = texture2D(uState, vUv - vec2(0.0, uTexel.y));
  vec4 east = texture2D(uState, vUv + vec2(uTexel.x, 0.0));
  vec4 west = texture2D(uState, vUv - vec2(uTexel.x, 0.0));
  vec4 average = (north + south + east + west) * 0.25;

  float body = state.r;
  float vessel = state.g;
  float activity = state.b * 0.986;
  float settled = min(1.0, state.a + 0.0015);

  if (uActive > 0.5) {
    float eased = 0.5 - 0.5 * cos(clamp(uProgress, 0.0, 1.0) * 3.14159265);
    vec2 tip = mix(uFrom, uTo, eased);
    float grain = noise(vUv * 23.0 + vec2(uSeed * 0.013, uSeed * 0.021));
    float fine = noise(vUv * 67.0 - vec2(uSeed * 0.017, uSeed * 0.009));
    float organicRadius = uRadius * mix(0.82, 1.18, grain) * mix(0.93, 1.07, fine);
    float capsule = segmentDistance(vUv, uFrom, tip);
    float lobe = length(vUv - tip);
    float pathWidth = mix(uRadius * 0.24, uRadius * 0.48, eased);
    float bodyInjection = max(
      smoothstep(pathWidth, pathWidth * 0.2, capsule),
      smoothstep(organicRadius, organicRadius * 0.14, lobe)
    );
    float veinInjection = max(
      smoothstep(uRadius * 0.11, uRadius * 0.018, capsule),
      smoothstep(uRadius * 0.17, uRadius * 0.025, lobe) * (0.35 + 0.65 * fine)
    );
    float local = smoothstep(uRadius * 2.6, uRadius * 0.25, min(capsule, lobe));

    body = max(body, bodyInjection * (0.78 + grain * 0.22));
    vessel = max(vessel, veinInjection);
    activity = max(activity, bodyInjection * (0.72 + 0.28 * eased));
    settled = min(settled, 1.0 - bodyInjection * 0.85);

    // Only the touched neighborhood relaxes. Distant tissue stays bit-stable.
    body += (average.r - body) * 0.035 * local;
    vessel += (average.g - vessel) * 0.012 * local;
  }

  gl_FragColor = clamp(vec4(body, vessel, activity, settled), 0.0, 1.0);
}`,g=`
precision highp float;
varying vec2 vUv;
uniform sampler2D uState;
uniform vec2 uTexel;
uniform float uTime;
uniform float uAspect;
uniform float uPulse;

float hash21(vec2 p) {
  p = fract(p * vec2(123.34, 456.21));
  p += dot(p, p + 45.32);
  return fract(p.x * p.y);
}

vec2 hash22(vec2 p) {
  float n = sin(dot(p, vec2(41.0, 289.0)));
  return fract(vec2(262144.0, 32768.0) * n);
}

float voronoiEdge(vec2 p) {
  vec2 cell = floor(p);
  vec2 f = fract(p);
  float nearest = 8.0;
  float second = 8.0;
  for (int y = -1; y <= 1; y++) {
    for (int x = -1; x <= 1; x++) {
      vec2 offset = vec2(float(x), float(y));
      vec2 point = offset + hash22(cell + offset) - f;
      float distanceSquared = dot(point, point);
      if (distanceSquared < nearest) {
        second = nearest;
        nearest = distanceSquared;
      } else if (distanceSquared < second) {
        second = distanceSquared;
      }
    }
  }
  return sqrt(second) - sqrt(nearest);
}

void main() {
  // Keep the specimen broad but unstretched on landscape and portrait screens.
  float fit = max(1.0, uAspect / 1.45);
  vec2 q = vec2((vUv.x - 0.5) * fit + 0.5, vUv.y);
  bool outside = q.x < 0.0 || q.x > 1.0 || q.y < 0.0 || q.y > 1.0;
  vec4 state = outside ? vec4(0.0) : texture2D(uState, q);
  float body = state.r;
  float vessel = state.g;
  float activity = state.b;

  float left = outside ? 0.0 : texture2D(uState, q - vec2(uTexel.x, 0.0)).r;
  float right = outside ? 0.0 : texture2D(uState, q + vec2(uTexel.x, 0.0)).r;
  float down = outside ? 0.0 : texture2D(uState, q - vec2(0.0, uTexel.y)).r;
  float up = outside ? 0.0 : texture2D(uState, q + vec2(0.0, uTexel.y)).r;
  float gradient = length(vec2(right - left, up - down));

  float mask = smoothstep(0.25, 0.5, body);
  float inner = smoothstep(0.48, 0.76, body);
  float membrane = smoothstep(0.018, 0.095, gradient) * smoothstep(0.12, 0.55, body);
  float outerField = smoothstep(0.08, 0.34, body) * (1.0 - mask);

  vec2 warp = vec2(
    sin(q.y * 19.0 + q.x * 7.0),
    cos(q.x * 17.0 - q.y * 5.0)
  ) * 0.38;
  float cellsLarge = voronoiEdge(q * 29.0 + warp);
  float cellsFine = voronoiEdge(q * 61.0 - warp * 0.7);
  float cellWall = (1.0 - smoothstep(0.025, 0.09, cellsLarge)) * 0.72
                 + (1.0 - smoothstep(0.018, 0.055, cellsFine)) * 0.28;
  cellWall *= mask * (0.35 + 0.65 * body);

  float pixelGrain = hash21(floor(q / uTexel));
  float stipple = step(pixelGrain, outerField * 0.7 + activity * 0.08);
  float breath = 0.78 + 0.22 * sin(uTime * 0.72 + q.x * 5.0 + q.y * 3.0);
  float livingEdge = membrane * mix(0.78, 1.18, breath) + outerField * stipple * 0.65;

  vec3 black = vec3(0.008, 0.009, 0.011);
  vec3 tissue = vec3(0.80, 0.77, 0.66);
  vec3 tissueShadow = vec3(0.10, 0.13, 0.12);
  vec3 core = vec3(1.0, 0.19, 0.035);
  vec3 membraneColor = vec3(0.16, 0.88, 0.82);

  vec3 color = black;
  color += vec3(0.012, 0.02, 0.021) * (1.0 - length(vUv - 0.5));
  color = mix(color, mix(tissueShadow, tissue, inner * 0.84), mask * 0.86);
  color = mix(color, tissue * 0.68, cellWall * (0.38 + 0.35 * inner));
  color = mix(color, tissueShadow * 0.45, cellWall * 0.33 * (1.0 - vessel));
  color += core * pow(vessel, 1.45) * (1.05 + activity * 0.42 + uPulse * 0.16);
  color += membraneColor * livingEdge * (0.62 + activity * 0.65);
  color += mix(tissue, membraneColor, 0.42) * stipple * outerField * 0.28;

  float vignette = smoothstep(0.9, 0.28, length((vUv - 0.5) * vec2(0.8, 1.0)));
  color *= 0.62 + 0.38 * vignette;
  gl_FragColor = vec4(color, 1.0);
}`,_=384,v=[{x:.48,y:.51,radius:.15,parent:-1},{x:.34,y:.57,radius:.105,parent:0},{x:.24,y:.68,radius:.082,parent:1},{x:.17,y:.58,radius:.065,parent:1},{x:.39,y:.72,radius:.095,parent:0},{x:.53,y:.7,radius:.12,parent:0},{x:.66,y:.61,radius:.11,parent:0},{x:.76,y:.72,radius:.083,parent:6},{x:.71,y:.43,radius:.13,parent:0},{x:.83,y:.35,radius:.075,parent:8},{x:.55,y:.3,radius:.1,parent:0},{x:.36,y:.32,radius:.09,parent:0},{x:.25,y:.25,radius:.062,parent:11}],y=(e,t,n)=>Math.max(t,Math.min(n,e)),b=e=>e-Math.floor(e),x=e=>b(Math.sin(e*91.733)*43758.5453123);function S(e,t,n,r,i,a){let o=i-n,s=a-r,c=e-n,l=t-r,u=y((c*o+l*s)/Math.max(1e-5,o*o+s*s),0,1);return Math.hypot(c-o*u,l-s*u)}function C(e){let t=new Float32Array(_*_*4);for(let n=0;n<_;n++)for(let r=0;r<_;r++){let i=(r+.5)/_,a=(n+.5)/_,o=0,s=0;for(let t=0;t<e.length;t++){let n=e[t],r=(i-n.x)/(n.radius*(.86+x(t+2)*.32)),c=(a-n.y)/(n.radius*(.72+x(t+9)*.44)),l=Math.sin((i*31+a*19+t)*2.1)*.035;if(o=Math.max(o,y(1.08-Math.hypot(r,c)+l,0,1)),n.parent>=0){let t=e[n.parent],r=S(i,a,t.x,t.y,n.x,n.y),c=y(1-r/(n.radius*.38),0,1),l=y(1-r/Math.max(.006,n.radius*.09),0,1);o=Math.max(o,c*.76),s=Math.max(s,l)}}let c=Math.hypot(i-e[0].x,a-e[0].y);s=Math.max(s,y(1-c/.085,0,1));let l=(n*_+r)*4;t[l]=o,t[l+1]=s,t[l+2]=0,t[l+3]=1}let n=new d(t,_,_,o,l);return n.needsUpdate=!0,n.minFilter=c,n.magFilter=c,n.wrapS=f,n.wrapT=f,n}function w(l,d){let b=new u({canvas:l,antialias:!1,alpha:!1,powerPreference:`high-performance`});b.setClearColor(131844,1);let S=new n(-1,1,1,-1,0,1),w=new e(2,2),T=new s,E=new s,D=C(v),O={type:p,format:o,minFilter:c,magFilter:c,depthBuffer:!1,stencilBuffer:!1},k=[new a(_,_,O),new a(_,_,O)];k.forEach(e=>{e.texture.wrapS=f,e.texture.wrapT=f});let A={uState:{value:D},uTexel:{value:new t(1/_,1/_)},uFrom:{value:new t(.5,.5)},uTo:{value:new t(.5,.5)},uRadius:{value:.08},uProgress:{value:0},uSeed:{value:1},uActive:{value:0},uCopy:{value:1}},j=new i({vertexShader:m,fragmentShader:h,uniforms:A});T.add(new r(w,j));let M={uState:{value:k[0].texture},uTexel:{value:new t(1/_,1/_)},uTime:{value:0},uAspect:{value:1},uPulse:{value:0}},N=new i({vertexShader:m,fragmentShader:g,uniforms:M});E.add(new r(w,N));let P=0,F=v.map(e=>({...e})),I=0,L=null,R=0,z=!1,B=!1,V=0,H=performance.now(),U=[],W=()=>{let e=1-P;A.uState.value=P<0?D:k[P].texture,b.setRenderTarget(k[e]),b.render(T,S),b.setRenderTarget(null),P=e,M.uState.value=k[P].texture},G=()=>{F=v.map(e=>({...e})),I=0,L=null,U.length=0,R=0,P=0,A.uCopy.value=1,A.uState.value=D,W(),A.uCopy.value=0,d({count:I,phase:z?`paused`:`resting`,message:`mature baseline · waiting for an event`,progress:0})},K=e=>{let n=800+I*37+(e===`novel`?17:0),r,i,a;if(e===`related`)r=1+Math.floor(x(n)*(F.length-1)),i=x(n+3)*Math.PI*2,a=.08+x(n+5)*.07;else{r=F.reduce((e,t,n)=>Math.hypot(t.x-.48,t.y-.51)>Math.hypot(F[e].x-.48,F[e].y-.51)?n:e,0);let e=F[r];i=Math.atan2(e.y-.51,e.x-.48)+(x(n+7)-.5)*.65,a=.14+x(n+11)*.08}let o=F[r],s=new t(y(o.x+Math.cos(i)*a,.08,.92),y(o.y+Math.sin(i)*a,.08,.92));return{kind:e,from:new t(o.x,o.y),to:s,radius:e===`novel`?.08+x(n+13)*.025:.052+x(n+13)*.02,seed:n,label:e===`novel`?`novel material · budding a new lobe`:`related material · reinforcing a living region`}},q=()=>{L||!U.length||z||(L=U.shift(),R=0,A.uFrom.value.copy(L.from),A.uTo.value.copy(L.to),A.uRadius.value=L.radius,A.uSeed.value=L.seed,A.uActive.value=1,d({count:I,phase:`growing`,message:L.label,progress:0}))},J=()=>{let e=l.clientWidth||innerWidth,t=l.clientHeight||innerHeight;b.setPixelRatio(Math.min(devicePixelRatio||1,2)),b.setSize(e,t,!1),M.uAspect.value=e/Math.max(1,t)},Y=e=>{if(B)return;let t=Math.min(.05,Math.max(.001,(e-H)/1e3));if(H=e,M.uTime.value+=t,!z&&(q(),L)){R+=t;let e=Math.min(1,R/2.6);if(A.uProgress.value=e,M.uPulse.value=Math.sin(e*Math.PI),W(),d({count:I,phase:`growing`,message:L.label,progress:e}),e>=1){F.push({x:L.to.x,y:L.to.y,radius:L.radius,parent:0}),I++;let e=L;L=null,A.uActive.value=0,M.uPulse.value=0,d({count:I,phase:`resting`,message:`${e.kind} event settled into permanent state`,progress:1})}}b.setRenderTarget(null),b.render(E,S),V=requestAnimationFrame(Y)};return J(),addEventListener(`resize`,J),G(),V=requestAnimationFrame(Y),{add(e){U.push(K(e)),q()},reset:G,setPaused(e){z=e,d({count:I,phase:e?`paused`:L?`growing`:`resting`,message:e?`simulation paused`:L?.label??`organism resumed`,progress:L?Math.min(1,R/2.6):0}),e||q()},destroy(){B=!0,cancelAnimationFrame(V),removeEventListener(`resize`,J),D.dispose(),k.forEach(e=>e.dispose()),j.dispose(),N.dispose(),w.dispose(),b.dispose()}}}export{w as mountGrowth};