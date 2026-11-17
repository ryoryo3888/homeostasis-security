"use strict";
(() => {
  const globe=document.getElementById('globe');
  if(!globe)return;
  const motion=matchMedia('(prefers-reduced-motion: reduce)');
  const node=(tag,cls,text)=>{
    const item=document.createElement(tag);
    if(cls)item.className=cls;
    if(text)item.textContent=text;
    return item;
  };
  const stage=node('div','hs-celestial'),view=node('div','hs-celestial-view');
  const sky=node('div','hs-normal-starfield'),planet=node('canvas','hs-earth-render');
  const lines=node('canvas','hs-earth-arcs');
  lines.setAttribute('aria-hidden','true');
  const controls=node('div','hs-earth-controls');
  const caption=node('small',null,'過去の衛星合成画像：');
  const nasaDay=node('a',null,'NASA/GSFC SVS'),nasaNight=node('a',null,'NASA Earth Observatory');
  nasaDay.href='https://svs.gsfc.nasa.gov/3615';
  nasaNight.href='https://science.nasa.gov/earth/earth-observatory/earth-at-night/maps/';
  sky.setAttribute('aria-hidden','true');
  planet.tabIndex=0;
  planet.setAttribute('aria-label','地球儀の向き：矢印キーで回転、プラスとマイナスで拡大縮小');
  caption.append(nasaDay,'・',nasaNight,'｜照明基準：2026/06/21 10:00 JST（演出）。星・光の弧は装飾。観測未接続。');
  view.append(sky,planet,lines);
  stage.append(view,controls,caption);
  globe.querySelector('span')?.classList.add('hs-wire-caption');
  globe.insertBefore(stage,globe.firstChild);
  let ready=false,visible=true,active=false,manual=false,frame=0,last=0;
  let latitude=1.704,longitude=118.928,zoom=1,drag=null;
  const wrap=x=>((x+180)%360+360)%360-180;
  const clamp=(x,min,max)=>Math.min(max,Math.max(min,x));
  const stars=globalThis.HS_NORMAL_STARFIELD?.mount(sky);
  const gl=planet.getContext('webgl2',{alpha:true,premultipliedAlpha:false,antialias:false});
  if(!gl){stars?.destroy();return;}
  const vertex=`#version 300 es
  const vec2 positions[3]=vec2[3](vec2(-1,-1),vec2(3,-1),vec2(-1,3));
  void main(){gl_Position=vec4(positions[gl_VertexID],0,1);}`;
  const fragment=`#version 300 es
  precision highp float;
  uniform sampler2D uDay, uNight;
  uniform vec2 uSize, uCamera, uSun;
  uniform float uZoom;
  out vec4 frag;
  const float PI=3.14159265359;
  const vec3 cold=vec3(.41,.69,.97),city=vec3(.97,.59,.21);
  float sm(float x){return smoothstep(0.,1.,x);}
  vec2 coordinates(vec2 pos){
    float z=sqrt(max(0.,1.-dot(pos,pos))),p=uCamera.x;
    return vec2(asin(clamp(pos.y*cos(p)+z*sin(p),-1.,1.)),
      uCamera.y+atan(pos.x,z*cos(p)-pos.y*sin(p)));
  }
  vec2 uv(vec2 ll){return vec2(ll.y/(2.*PI)+.5,.5-ll.x/PI);}
  float insolation(vec2 ll){return sin(ll.x)*sin(uSun.x)+cos(ll.x)*cos(uSun.x)*cos(ll.y-uSun.y);}
  float cloud(vec3 tex,float lat,float mu,float q){
    return sm((dot(tex,vec3(.2126,.7152,.0722))-.37)/.36)*sm((tex.b-tex.r+.058)/.11)
          *sm((.91-abs(lat))/.15)*sm((mu+.013)/.32)*sm((1.-q)/.048);
  }
  float witness(vec2 at){
    vec2 ll=coordinates(at);
    return cloud(texture(uDay,uv(ll)).rgb,ll.x,insolation(ll),length(at));
  }
  vec3 cobalt(float f){
    const vec3 c[6]=vec3[6](vec3(2,7,53),vec3(3,8,82),vec3(6,10,114),vec3(12,20,143),vec3(16,29,163),vec3(25,87,187));
    float v=clamp(f,0.,1.)*5.; int i=min(4,int(v));
    return mix(c[i],c[i+1],v-float(i))/255.;
  }
  void main(){
    float radius=min(uSize.x,uSize.y)*.45*uZoom;
    vec2 at=(gl_FragCoord.xy-uSize*.5)/radius;
    float q=length(at),z=sqrt(max(0.,1.-q*q)),p=uCamera.x;
    vec2 ll=coordinates(q>1.?at/q:at);
    float mu=insolation(ll),side=.10+.90*sm((mu+.24)/1.02);
    if(q>1.){
      float r=(q-1.)*radius,scale=max(radius/410.,.42);
      float a=side*(.58*exp(-r/(2.*scale))+.125*exp(-r/(8.7*scale)));
      frag=a>.004?vec4(vec3(.30,.53,.84),a):vec4(0); return;
    }
    vec3 day=texture(uDay,uv(ll)).rgb,night=texture(uNight,uv(ll)).rgb;
    float water=sm((day.b-day.r-.021)/.22)*sm((day.b-day.g+.038)/.16);
    float warm=sm((day.r-day.b-.03)/.29)*(1.-sm((day.r-.62)/.35));
    vec3 toned=day*vec3(1.-.24*water-.11*warm,1.-.20*water,1.-.045*water);
    toned.b+=.032*warm;
    float exposure=.010+.25*sm((mu+.018)/.57)+.69*pow(max(0.,mu),.62);
    vec3 linear=pow(toned,vec3(2.18))*exposure*vec3(.987,1.011,1.034);
    float density=clamp((night.r+night.g-.095)/1.1,0.,1.);
    float cityPower=(1.-sm((abs(ll.x)-1.10)/.20))*(1.-sm((mu+.19)/.24))*
      (.034*sm(density/.31)+.53*sm((density-.12)/.72));
    linear=mix(linear,city,cityPower);
    vec3 atm=side*(pow(1.-z,17.)*cold+pow(1.-z,4.5)*vec3(.005,.027,.061));
    linear+= (1.-linear)*atm;
    vec3 outc=pow(clamp(linear,0.,1.),vec3(1./2.2));
    float strength=.99*sm((water-.16)/.71)*sm((outc.b-outc.r-.022)/.19)
      *(1.-sm((outc.r-.25)/.28))*(1.-.94*sm((1.-z-.66)/.34))*sm((outc.b-.06)/.17)
      *(1.-.48*sm((outc.g-.45)/.49)*sm((outc.b-.41)/.47));
    outc=mix(outc,cobalt((.85*outc.b+.15*outc.g-.115)/.65),strength);
    // A few directional samples of baked cloud brightness give optical relief,
    // not independently measured or moved clouds, coast, or ice.
    vec2 solar=vec2(cos(uSun.x)*sin(uSun.y-uCamera.y),
      sin(uSun.x)*cos(p)-cos(uSun.x)*cos(uSun.y-uCamera.y)*sin(p));
    solar/=max(length(solar),.05);
    float w=cloud(day,ll.x,mu,q);
    float a=witness(at+solar*.0083),b=witness(at-solar*.0083);
    float shadow=.28*sm(max(witness(at+solar*.017)-1.07*w,0.)/.32)*
       sm((water-.51)/.36)*(1.-sm(w/.22))*sm((mu+.019)/.32)*sm((1.-q)/.071);
    float slope=clamp((b-a)*3.4,-1.,1.),cap=sm((w-.18)/.63);
    outc=outc*(1.-shadow)*(1.-cap*(.185*max(-slope,0.)+.044*sm((.75-w)/.53)));
    outc+=cap*(.125*max(slope,0.)+.075*sm((w-.46)/.49))*(vec3(.92,.955,1.)-outc);
    frag=vec4(outc,1.);
  }`;
  function shader(type,source){
    const id=gl.createShader(type);
    gl.shaderSource(id,source);gl.compileShader(id);
    if(!gl.getShaderParameter(id,gl.COMPILE_STATUS)){gl.deleteShader(id);return null;}
    return id;
  }
  const vs=shader(gl.VERTEX_SHADER,vertex),fs=shader(gl.FRAGMENT_SHADER,fragment);
  if(!vs||!fs){stars?.destroy();return;}
  const program=gl.createProgram();
  gl.attachShader(program,vs);gl.attachShader(program,fs);gl.linkProgram(program);
  gl.deleteShader(vs);gl.deleteShader(fs);
  if(!gl.getProgramParameter(program,gl.LINK_STATUS)){stars?.destroy();return;}
  gl.useProgram(program);
  const locate=n=>gl.getUniformLocation(program,n);
  const size=locate('uSize'),camera=locate('uCamera');
  const distance=locate('uZoom'),sun=locate('uSun');
  gl.uniform1i(locate('uDay'),0);gl.uniform1i(locate('uNight'),1);
  // Geographic Sun direction is fixed to the approved presentation reference,
  // rather than following the frame count, terminal clock or simulated world.
  const angle=2*Math.PI/365*(172+(1-12)/24);
  const equation=229.18*(.000075+.001868*Math.cos(angle)-.032077*Math.sin(angle)-.014615*Math.cos(2*angle)-.040849*Math.sin(2*angle));
  const declination=.006918-.399912*Math.cos(angle)+.070257*Math.sin(angle)-.006758*Math.cos(2*angle)+.000907*Math.sin(2*angle)-.002697*Math.cos(3*angle)+.00148*Math.sin(3*angle);
  const radians=Math.PI/180;
  gl.uniform2f(sun,declination,(165-equation/4)*radians);
  const arcContext=lines.getContext('2d');
  const vector=(p,l)=>[Math.cos(p)*Math.cos(l),Math.cos(p)*Math.sin(l),Math.sin(p)];
  const dot=(a,b)=>a[0]*b[0]+a[1]*b[1]+a[2]*b[2];
  // Decorative examples generated from angles, not observed routes or points.
  const strokes=[
    [-4,100,40,148,.065,105], [25,120,-24,160,.073,101],
    [-23,128,36,170,.086,94], [11,82,12,179,.083,99],
    [-35,111,23,152,.070,82], [16,149,-15,189,.080,77],
    [-34,87,19,191,.064,63]
  ].map(([p1,l1,p2,l2,height,alpha])=>{
    const a=vector(p1*radians,l1*radians),b=vector(p2*radians,l2*radians);
    const angle=Math.acos(clamp(dot(a,b),-1,1)),den=Math.sin(angle);
    const points=Array.from({length:64},(_,i)=>{
      const t=i/63,left=Math.sin((1-t)*angle)/den,right=Math.sin(t*angle)/den;
      const raise=1+height*Math.sin(Math.PI*t);
      return a.map((x,j)=>(left*x+right*b[j])*raise);
    });
    return {points,alpha};
  });
  function drawArcs(w,h){
    if(!arcContext)return;
    if(lines.width!==w)lines.width=w;
    if(lines.height!==h)lines.height=h;
    const c=arcContext;c.clearRect(0,0,w,h);
    const p=latitude*radians,l=longitude*radians;
    const east=[-Math.sin(l),Math.cos(l),0],
      north=[-Math.sin(p)*Math.cos(l),-Math.sin(p)*Math.sin(l),Math.cos(p)], front=vector(p,l);
    const r=Math.min(w,h)*.45*zoom;
    c.lineWidth=Math.max(1,w/600);c.lineCap='round';
    for(const {points,alpha} of strokes){
      let previous;
      for(let i=0;i<points.length;i++){
        const a=points[i],x=dot(a,east),y=dot(a,north),z=dot(a,front);
        const next=[w/2+x*r,h/2-y*r,z>=0||x*x+y*y>=1.006];
        if(previous?.[2]&&next[2]){
          const weight=.30+.70*Math.max(0,Math.sin(Math.PI*(i/63)))**.63;
          const light=Math.min(1,1.54*alpha*weight*(z<0?.33:.64+.36*z)/255);
          c.strokeStyle='rgba(93,178,240,'+light.toFixed(3)+')';
          c.beginPath();c.moveTo(previous[0],previous[1]);c.lineTo(next[0],next[1]);c.stroke();
        }
        previous=next;
      }
    }
  }
  function upload(image,unit){
    gl.activeTexture(gl.TEXTURE0+unit);
    const tex=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,tex);
    gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR_MIPMAP_LINEAR);
    gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.REPEAT);
    gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
    gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,image);
    gl.generateMipmap(gl.TEXTURE_2D);
  }
  const load=path=>new Promise((resolve,reject)=>{
    const img=new Image();img.onload=()=>resolve(img);img.onerror=reject;img.src=path;
  });
  function draw(){
    if(!ready||!active||gl.isContextLost())return;
    const area=view.getBoundingClientRect();
    if(area.width<1||area.height<1)return;
    const scale=Math.min(window.devicePixelRatio||1,960/Math.max(area.width,area.height));
    const w=Math.max(1,Math.round(area.width*scale)),h=Math.max(1,Math.round(area.height*scale));
    if(planet.width!==w)planet.width=w;
    if(planet.height!==h)planet.height=h;
    gl.viewport(0,0,w,h);
    gl.uniform2f(size,w,h);gl.uniform2f(camera,latitude*radians,longitude*radians);
    gl.uniform1f(distance,zoom);gl.drawArrays(gl.TRIANGLES,0,3);drawArcs(w,h);
  }
  function stop(){cancelAnimationFrame(frame);frame=0;last=0;}
  function animate(t){
    if(!active||manual||motion.matches||document.hidden){stop();return;}
    if(!last||t-last>=1000/28){
      if(last)longitude=wrap(longitude+.844*Math.min(180,t-last)/1000);
      last=t;draw();
    }
    frame=requestAnimationFrame(animate);
  }
  function sync(){
    active=ready&&visible&&!document.hidden&&document.body.dataset.layout==='normal'&&globe.classList.contains('primary');
    stars?.setActive(active&&!manual&&!motion.matches);
    cancel.disabled=motion.matches||manual;
    cancel.textContent=manual||motion.matches?'自動演出停止中':'自動演出を停止';
    if(active){draw();if(!frame&&!manual&&!motion.matches)frame=requestAnimationFrame(animate);}
    if(!active)stop();
  }
  function interact(){manual=true;stop();sync();}
  function changeZoom(diff){interact();zoom=clamp(zoom+diff,1,1.8);draw();}
  function button(label,fn){
    const element=node('button',null,label);element.type='button';
    element.addEventListener('click',fn);controls.append(element);return element;
  }
  const cancel=button('自動演出を停止',interact);
  button('拡大',()=>changeZoom(.16));button('縮小',()=>changeZoom(-.16));
  button('初期位置',()=>{interact();longitude=118.928;latitude=1.704;zoom=1;draw();});
  planet.addEventListener('pointerdown',e=>{
    if(e.button!==0)return;
    interact();drag=[e.pointerId,e.clientX,e.clientY];planet.setPointerCapture(e.pointerId);
  });
  planet.addEventListener('pointermove',e=>{
    if(drag?.[0]!==e.pointerId)return;
    longitude=wrap(longitude-(e.clientX-drag[1])*.24/zoom);
    latitude=clamp(latitude+(e.clientY-drag[2])*.24/zoom,-84,84);
    drag=[e.pointerId,e.clientX,e.clientY];draw();
  });
  for(const type of ['pointerup','pointercancel','lostpointercapture'])planet.addEventListener(type,()=>{drag=null;});
  planet.addEventListener('keydown',e=>{
    const delta={ArrowLeft:[-4,0],ArrowRight:[4,0],ArrowUp:[0,4],ArrowDown:[0,-4]}[e.key];
    if(delta){e.preventDefault();interact();longitude=wrap(longitude+delta[0]);latitude=clamp(latitude+delta[1],-84,84);draw();}
    if(['+','=','-'].includes(e.key)){e.preventDefault();changeZoom(e.key==='-'?-.16:.16);}
  });
  planet.addEventListener('webglcontextlost',()=>{
    ready=false;delete globe.dataset.celestialReady;sync();
  });
  const observer=new MutationObserver(sync);
  observer.observe(globe,{attributes:true,attributeFilter:['class']});
  observer.observe(document.body,{attributes:true,attributeFilter:['data-layout']});
  new ResizeObserver(draw).observe(view);
  new IntersectionObserver(([event])=>{visible=event.isIntersecting;sync();}).observe(globe);
  document.addEventListener('visibilitychange',sync);
  motion.addEventListener('change',()=>{if(motion.matches)stop();sync();});
  Promise.all([load('assets/globe-surface.webp'),load('assets/normal-night-2016.webp')]).then(images=>{
    const max=gl.getParameter(gl.MAX_TEXTURE_SIZE);
    if(images.some(i=>i.naturalWidth>max||i.naturalHeight>max)||gl.isContextLost())return;
    images.forEach(upload);if(gl.getError()!==gl.NO_ERROR)return;
    ready=true;globe.dataset.celestialReady='true';sync();stars?.redraw();
  }).catch(()=>{}); // Keep the existing accessible wireframe if local assets or WebGL fail.
})();
