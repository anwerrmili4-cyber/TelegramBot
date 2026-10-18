import{n as e}from"./rolldown-runtime-CbXtAM7H.js";import{i as t,t as n}from"./react-vendor-DfSeidf4.js";var r=e(t(),1),i=n(),a=24e5,o=4,s={"top-left":{anchor:[0,-.2],dir:[0,1]},"top-center":{anchor:[.5,-.2],dir:[0,1]},"top-right":{anchor:[1,-.2],dir:[0,1]},left:{anchor:[-.2,.5],dir:[1,0]},right:{anchor:[1.2,.5],dir:[-1,0]},"bottom-left":{anchor:[0,1.2],dir:[0,-1]},"bottom-center":{anchor:[.5,1.2],dir:[0,-1]},"bottom-right":{anchor:[1,1.2],dir:[0,-1]}},c=`#version 300 es
const vec2 corners[3] = vec2[3](vec2(-1.0, -1.0), vec2(3.0, -1.0), vec2(-1.0, 3.0));
void main() {
  gl_Position = vec4(corners[gl_VertexID], 0.0, 1.0);
}`,l=`#version 300 es
precision highp float;
uniform vec2 uResolution;
uniform float uScale;
uniform float uTime;
uniform vec2 uSource;
uniform vec2 uAim;
uniform float uReach;
uniform vec3 uColor;
uniform float uSpread;
uniform float uLength;
uniform float uFade;
uniform float uSaturation;
uniform float uPulsating;
uniform float uNoise;
uniform float uDistortion;
uniform float uDensity;
uniform float uSharpness;
uniform float uGlow;
uniform float uHaze;
uniform float uAtmosphere;
uniform float uIntensity;
uniform vec4 uShadow;
uniform vec4 uPulses[${o}];
uniform vec2 uIntro;
uniform float uLight;
uniform float uOpacity;
out vec4 fragColor;

float hash(vec2 p) {
  p = fract(p * vec2(123.34, 456.21));
  p += dot(p, p + 45.32);
  return fract(p.x * p.y);
}

float valueNoise(vec2 p) {
  vec2 i = floor(p);
  vec2 f = p - i;
  vec2 w = f * f * f * (f * (f * 6.0 - 15.0) + 10.0);
  return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), w.x), mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), w.x), w.y);
}

float shape(float strength, float width) {
  float edge = max(mix(0.5, 0.08, uSharpness), width);
  return mix(strength, smoothstep(0.62 - edge, 0.62 + edge, strength), uSharpness);
}

void main() {
  vec2 coord = vec2(gl_FragCoord.x, uResolution.y - gl_FragCoord.y) / uScale;
  vec2 delta = coord - uSource;
  float distance = length(delta);
  vec2 dir = delta / max(distance, 1e-4);
  float cosAngle = dot(dir, uAim);
  float angle = cosAngle + uDistortion * sin(uTime * 2.0 + distance * 0.02) * 0.2;
  float slope = fwidth(angle);
  float depth = distance / uReach;

  float source = exp(-depth * depth * 9.0) * 0.9 + exp(-depth * 3.2) * 0.25;
  float glowLight = uGlow * source * smoothstep(-0.2, 0.6, cosAngle);
  float spread = pow(max(angle, 0.0), 1.0 / uSpread);
  float lengthFalloff = clamp(1.0 - distance / (uReach * uLength), 0.0, 1.0);
  float fadeFalloff = clamp(1.0 - distance / (uReach * uFade), 0.5, 1.0);
  float envelope = spread * lengthFalloff * fadeFalloff;
  float reveal = uIntensity * uIntro.y * (1.0 - smoothstep(uIntro.x - 0.35, uIntro.x, depth));
  if ((envelope * 1.6 + glowLight) * reveal < 0.0015) {
    fragColor = vec4(0.0);
    return;
  }

  float phaseA = angle * 36.2214 * uDensity + uTime * 1.5;
  float phaseB = -angle * 21.11349 * uDensity + uTime * 1.5;
  float phaseC = angle * 22.3991 * uDensity + uTime * 1.1;
  float phaseD = -angle * 18.0234 * uDensity + uTime * 1.1;
  float strengthA = clamp(0.75 + 0.15 * sin(phaseA) + 0.2 * cos(phaseB), 0.0, 1.0);
  float strengthB = clamp(0.75 + 0.15 * sin(phaseC) + 0.2 * cos(phaseD), 0.0, 1.0);
  float widthA = abs(0.15 * 36.2214 * cos(phaseA) + 0.2 * 21.11349 * sin(phaseB)) * uDensity * slope;
  float widthB = abs(0.15 * 22.3991 * cos(phaseC) + 0.2 * 18.0234 * sin(phaseD)) * uDensity * slope;
  float pulseA = uPulsating > 0.5 ? 0.8 + 0.2 * sin(uTime * 4.5) : 1.0;
  float pulseB = uPulsating > 0.5 ? 0.8 + 0.2 * sin(uTime * 3.3) : 1.0;
  float rayLight = envelope * (0.5 * shape(strengthA, widthA) * pulseA + 0.4 * shape(strengthB, widthB) * pulseB);

  if (uHaze > 0.0) {
    float around = atan(uAim.x * dir.y - uAim.y * dir.x, cosAngle);
    vec2 drift = vec2(around * 2.2 + uTime * 0.035, depth * 2.6 - uTime * 0.11);
    float fog = 0.65 * valueNoise(drift * vec2(3.0, 1.0)) + 0.35 * valueNoise(drift * vec2(7.0, 2.3) + 4.1);
    rayLight *= mix(1.0, 0.25 + 1.2 * fog, uHaze);
  }

  if (uShadow.z > 0.0) {
    vec2 toCursor = uShadow.xy - uSource;
    float cursorDistance = length(toCursor);
    float along = dot(delta, toCursor) / max(cursorDistance * cursorDistance, 1e-4);
    float side = abs(delta.x * toCursor.y - delta.y * toCursor.x) / max(cursorDistance, 1e-4);
    float trail = max(along - 1.0, 0.0);
    float width = uShadow.w * along + 0.22 * trail * cursorDistance;
    float behind = smoothstep(0.97, 1.25, along) * exp(-trail * 1.1);
    float shade = (1.0 - smoothstep(width * 0.3, width * 1.6, side)) * behind;
    rayLight *= 1.0 - uShadow.z * 0.62 * shade;
  }

  float boost = 0.0;
  for (int i = 0; i < ${o}; i++) {
    vec4 wave = uPulses[i];
    if (wave.z <= 0.0) continue;
    float x = (depth - wave.x) / wave.y;
    boost += wave.z * exp(-x * x);
  }
  float light = (rayLight * (1.0 + boost) + glowLight) * reveal;

  if (uNoise > 0.0) {
    float n = fract(sin(dot(coord * 0.02 + uTime * 0.1, vec2(12.9898, 78.233))) * 43758.5453123);
    light *= 1.0 - uNoise + uNoise * n;
  }

  float near = clamp(1.2 - distance / (uResolution.y / uScale), 0.0, 1.0);
  vec3 tint = mix(vec3(0.9), vec3(0.1, 0.3, 0.5) + near * vec3(0.8, 0.6, 0.5), uAtmosphere);
  float gray = dot(tint, vec3(0.299, 0.587, 0.114));
  vec3 hue = max(mix(vec3(gray), tint, uSaturation), 0.0) * uColor;

  float grain = (fract(52.9829189 * fract(dot(gl_FragCoord.xy, vec2(0.06711056, 0.00583715)))) - 0.5) / 255.0;
  if (uLight > 0.5) {
    vec3 color = hue * light;
    float energy = max(color.r, max(color.g, color.b));
    vec3 tone = clamp(1.0 - (1.0 - hue / max(max(hue.r, max(hue.g, hue.b)), 1e-4)) * 1.8, 0.0, 1.0);
    float warm = clamp((min(tone.r, tone.g) - tone.b) * 2.0, 0.0, 1.0);
    vec3 ink = tone * (mix(0.66, 0.94, warm) - 0.1 * smoothstep(0.4, 1.2, energy));
    float density = clamp(0.82 * (1.0 - exp(-1.5 * energy * energy)) * uOpacity + grain, 0.0, 1.0);
    fragColor = vec4(ink * density, density);
    return;
  }
  float level = light < 0.75 ? light : 0.75 + 0.25 * (1.0 - exp(-(light - 0.75) / 0.25));
  float top = max(hue.r, max(hue.g, hue.b));
  hue = mix(hue, vec3(top), smoothstep(0.8, 1.0, level) * 0.45);
  vec3 shown = clamp(hue * level, 0.0, 1.0) * level;
  fragColor = vec4(clamp(shown + grain, 0.0, level) * uOpacity, level * uOpacity);
}`,u=(e,t,n)=>Math.min(n,Math.max(t,e)),d=e=>{let t=String(e||``).trim(),n=/^#?([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(t);if(n){let e=n[1].length===3?n[1].replace(/./g,e=>e+e):n[1];return[0,2,4].map(t=>parseInt(e.slice(t,t+2),16)/255)}let r=/^rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)/i.exec(t);return r?[r[1],r[2],r[3]].map(e=>u(parseFloat(e)/255,0,1)):null},f=(e,t,n)=>{let r=e.createShader(t);return r?(e.shaderSource(r,n),e.compileShader(r),e.getShaderParameter(r,e.COMPILE_STATUS)?r:(console.error(e.getShaderInfoLog(r)),e.deleteShader(r),null)):null},p=e=>{let t=f(e,e.VERTEX_SHADER,c),n=f(e,e.FRAGMENT_SHADER,l),r=t&&n?e.createProgram():null;if(!t||!n||!r)return t&&e.deleteShader(t),n&&e.deleteShader(n),null;if(e.attachShader(r,t),e.attachShader(r,n),e.linkProgram(r),e.deleteShader(t),e.deleteShader(n),!e.getProgramParameter(r,e.LINK_STATUS))return console.error(e.getProgramInfoLog(r)),e.deleteProgram(r),null;let i={},a=e.getProgramParameter(r,e.ACTIVE_UNIFORMS);for(let t=0;t<a;t++){let n=e.getActiveUniform(r,t);n&&(i[n.name.replace(/\[0\]$/,``)]=e.getUniformLocation(r,n.name))}return{program:r,uniforms:i}},m=e=>{let t=u(e,0,1);return t*t*t*(t*(t*6-15)+10)},h=({raysOrigin:e=`top-center`,raysColor:t=`#ffffff`,raysSpeed:n=1,lightSpread:c=.5,rayLength:l=3,rayDensity:f=1,tilt:h=0,raySharpness:g=.35,glow:_=.6,haze:v=.25,atmosphere:y=1,intensity:b=1,pulsating:x=!1,fadeDistance:S=1,saturation:C=1,followMouse:w=!0,mouseInfluence:T=.1,cursorShadow:E=!0,clickPulse:D=!0,noiseAmount:O=0,distortion:k=0,intro:A=!0,lightMode:j=!1,opacity:M=1,maxDevicePixelRatio:N=2,className:P=``,style:F})=>{let I=(0,r.useRef)(null),L=(0,r.useRef)(null),R=(0,r.useRef)(null),z=(0,r.useRef)(0),[B,V]=(0,r.useState)(0),H={origin:s[e]||s[`top-center`],color:d(t)||[1,1,1],speed:Math.max(0,n),spread:Math.max(.001,c),length:Math.max(.01,l),density:u(f,.1,6),tilt:u(h,-90,90)*Math.PI/180,sharpness:u(g,0,1),glow:Math.max(0,_),haze:u(v,0,1),atmosphere:u(y,0,1),intensity:Math.max(0,b),pulsating:x,fade:Math.max(.01,S),saturation:Math.max(0,C),follow:w,influence:u(T,0,1),cursorShadow:E,clickPulse:D,noise:u(O,0,1),distortion:k,intro:A,light:j,opacity:u(M,0,1),maxRatio:u(N,.5,3)},U=(0,r.useRef)(H);return U.current=H,(0,r.useEffect)(()=>{R.current?.()}),(0,r.useEffect)(()=>{let e=I.current,t=L.current;if(!e||!t)return;let n=t.getContext(`webgl2`,{alpha:!0,premultipliedAlpha:!0,antialias:!1,depth:!1,stencil:!1,powerPreference:`high-performance`});if(n?.isContextLost()){t.style.visibility=`hidden`;let e=()=>V(e=>e+1);return t.addEventListener(`webglcontextrestored`,e),()=>{t.style.visibility=``,t.removeEventListener(`webglcontextrestored`,e)}}let r=n?p(n):null;if(!n||!r)return;let i=window.matchMedia(`(prefers-reduced-motion: reduce)`).matches,s=n.createVertexArray(),c={width:1,height:1,ratio:1},l={x:.5,y:.5,inside:!1,seen:!1},d={x:.5,y:.5},f={x:.5,y:.5,presence:0},h=[],g=new Float32Array(16),_=0,v=U.current.intro&&!i&&B===0?0:1,y=0,b=0,x=!0,S=document.visibilityState!==`hidden`,C=!1,w=()=>{let n=U.current,r=e.getBoundingClientRect(),i=Math.max(1,r.width),o=Math.max(1,r.height),s=n.density*(.35+.65*n.sharpness),l=Math.max(u(.35+.3*s,.5,2),+(n.noise>0)),d=Math.min(window.devicePixelRatio||1,n.maxRatio,l,Math.sqrt(a/(i*o))),f=Math.max(1,Math.round(i*d)),p=Math.max(1,Math.round(o*d));(t.width!==f||t.height!==p)&&(t.width=f,t.height=p),c.width=i,c.height=o,c.ratio=f/i},T=e=>{if(y=0,C)return;let a=U.current,o=u((e-b)/1e3||0,0,.05);b=Math.max(b,e),_+=o*a.speed*(i?.35:1),v<1&&(v=Math.min(1,v+o/1.8));let p=1-Math.exp(-o/.2),w=a.follow&&l.seen?l.x:.5,E=a.follow&&l.seen?l.y:.5;d.x+=(w-d.x)*p,d.y+=(E-d.y)*p;let D=1-Math.exp(-o/.08);f.x+=(l.x-f.x)*D,f.y+=(l.y-f.y)*D;let O=l.inside&&a.cursorShadow&&!i;f.presence+=(+!!O-f.presence)*(1-Math.exp(-o/(O?.25:.5)));for(let e=h.length-1;e>=0;e--)h[e].age+=o,h[e].age>=2&&h.splice(e,1);g.fill(0),h.forEach((e,t)=>{let n=e.age;g[t*4]=.05+n*1.05,g[t*4+1]=.14+n*.14,g[t*4+2]=.9*m(n/.15)*(1-m(n/2))});let k=c.width,A=c.height,j=a.origin.anchor[0]*k,M=a.origin.anchor[1]*A,N=Math.cos(a.tilt),P=Math.sin(a.tilt),F=a.origin.dir[0]*N-a.origin.dir[1]*P,I=a.origin.dir[0]*P+a.origin.dir[1]*N;if(a.follow&&a.influence>0){let e=d.x*k-j,t=d.y*A-M,n=Math.hypot(e,t)||1,r=F+(e/n-F)*a.influence,i=I+(t/n-I)*a.influence,o=Math.hypot(r,i)||1;F=r/o,I=i/o}let L=1-(1-v)**3;n.viewport(0,0,t.width,t.height),n.clearColor(0,0,0,0),n.clear(n.COLOR_BUFFER_BIT),n.useProgram(r.program),n.bindVertexArray(s);let R=r.uniforms;n.uniform2f(R.uResolution,t.width,t.height),n.uniform1f(R.uScale,c.ratio),n.uniform1f(R.uTime,_),n.uniform2f(R.uSource,j,M),n.uniform2f(R.uAim,F,I),n.uniform1f(R.uReach,Math.max(k,A)),n.uniform3f(R.uColor,a.color[0],a.color[1],a.color[2]),n.uniform1f(R.uSpread,a.spread),n.uniform1f(R.uLength,a.length),n.uniform1f(R.uFade,a.fade),n.uniform1f(R.uSaturation,a.saturation),n.uniform1f(R.uPulsating,+!!a.pulsating),n.uniform1f(R.uNoise,a.noise),n.uniform1f(R.uDistortion,a.distortion),n.uniform1f(R.uDensity,a.density),n.uniform1f(R.uSharpness,a.sharpness),n.uniform1f(R.uGlow,a.glow),n.uniform1f(R.uHaze,a.haze),n.uniform1f(R.uAtmosphere,a.atmosphere),n.uniform1f(R.uIntensity,a.intensity),n.uniform4f(R.uShadow,f.x*k,f.y*A,f.presence,16),n.uniform4fv(R.uPulses,g),n.uniform2f(R.uIntro,L*2.6,m(v/.5)),n.uniform1f(R.uLight,+!!a.light),n.uniform1f(R.uOpacity,a.opacity),n.drawArrays(n.TRIANGLES,0,3);let z=Math.abs(d.x-w)>1e-4||Math.abs(d.y-E)>1e-4||f.presence>.001&&Math.abs(f.x-l.x)+Math.abs(f.y-l.y)>1e-4||Math.abs(+!!O-f.presence)>.001||h.length>0;(a.speed>0||v<1||z)&&x&&S&&(y=requestAnimationFrame(T))},E=()=>{y||C||!x||!S||(b=performance.now(),y=requestAnimationFrame(T))};R.current=()=>{w(),E()};let D=t=>{let n=e.getBoundingClientRect();return{x:(t.clientX-n.left)/Math.max(1,n.width),y:(t.clientY-n.top)/Math.max(1,n.height),inside:t.clientX>=n.left&&t.clientX<=n.right&&t.clientY>=n.top&&t.clientY<=n.bottom}},O=e=>{let t=D(e);!l.inside&&t.inside&&(f.x=t.x,f.y=t.y),l.x=t.x,l.y=t.y,l.inside=t.inside,l.seen=!0,E()},k=e=>{let t=U.current;!D(e).inside||!t.clickPulse||i||(h.push({age:0}),h.length>o&&h.shift(),E())},A=()=>{l.inside=!1,E()},j=e=>{e.pointerType!==`mouse`&&A()};(U.current.follow||U.current.clickPulse)&&(window.addEventListener(`pointermove`,O,{passive:!0}),window.addEventListener(`pointerdown`,k,{passive:!0}),window.addEventListener(`pointerup`,j,{passive:!0}),window.addEventListener(`pointercancel`,j,{passive:!0}),document.documentElement.addEventListener(`pointerleave`,A));let M=e=>{e.preventDefault(),C=!0,t.style.visibility=`hidden`,cancelAnimationFrame(y),y=0},N=()=>V(e=>e+1);t.addEventListener(`webglcontextlost`,M),t.addEventListener(`webglcontextrestored`,N);let P=new ResizeObserver(()=>{w(),E()});P.observe(e);let F=new IntersectionObserver(e=>{x=e.some(e=>e.isIntersecting),E()});F.observe(e);let H=()=>{S=document.visibilityState!==`hidden`,E()};document.addEventListener(`visibilitychange`,H),w(),E();let W=++z.current;return()=>{cancelAnimationFrame(y),R.current=null,P.disconnect(),F.disconnect(),window.removeEventListener(`pointermove`,O),window.removeEventListener(`pointerdown`,k),window.removeEventListener(`pointerup`,j),window.removeEventListener(`pointercancel`,j),document.documentElement.removeEventListener(`pointerleave`,A),document.removeEventListener(`visibilitychange`,H),t.removeEventListener(`webglcontextlost`,M),t.removeEventListener(`webglcontextrestored`,N),t.style.visibility=``,requestAnimationFrame(()=>{z.current!==W||n.isContextLost()||(n.deleteVertexArray(s),n.deleteProgram(r.program),n.getExtension(`WEBGL_lose_context`)?.loseContext())})}},[B]),(0,i.jsx)(`div`,{ref:I,className:`light-rays${P?` ${P}`:``}`,style:F,children:(0,i.jsx)(`canvas`,{ref:L,className:`light-rays__canvas`,"aria-hidden":`true`})})};export{h as default};