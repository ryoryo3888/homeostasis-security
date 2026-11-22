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
  const twinCaption=node('small',null,'デジタルツイン表示（地理・配色の見本）｜Natural Earth 1:50m。シアン実線：輪郭・国境、シアン点線：経緯線、暖色破線：係争・管理線など。現在の観測・演算結果ではありません。');
  twinCaption.hidden=true;
  const nasaDay=node('a',null,'NASA/GSFC SVS'),nasaNight=node('a',null,'NASA Earth Observatory');
  nasaDay.href='https://svs.gsfc.nasa.gov/3615';
  nasaNight.href='https://science.nasa.gov/earth/earth-observatory/earth-at-night/maps/';
  sky.setAttribute('aria-hidden','true');
  planet.tabIndex=0;
  planet.setAttribute('aria-label','地球儀の向き：矢印キーで回転、プラスとマイナスで拡大縮小');
  caption.append(nasaDay,'・',nasaNight,'｜照明基準：2026/06/21 10:00 JST（演出）。星・光の弧は装飾。観測未接続。');
  view.append(sky,planet,lines);
  stage.append(view,controls,caption,twinCaption);
  globe.querySelector('span')?.classList.add('hs-wire-caption');
  globe.insertBefore(stage,globe.firstChild);
  let ready=false,visible=true,active=false,manual=false,frame=0,last=0;
  let latitude=1.704,longitude=118.928,zoom=1,drag=null;
  const wrap=x=>((x+180)%360+360)%360-180;
  const clamp=(x,min,max)=>Math.min(max,Math.max(min,x));
  const stars=globalThis.HS_NORMAL_STARFIELD?.mount(sky);
  // Keep the interactive element independent of graphics backends so focus,
  // pointer capture and the camera survive WebGL initialization or context loss.
  const output=planet.getContext('2d');
  if(!output){stars?.destroy();return;}
  const gpuCanvas=document.createElement('canvas');
  let gl=null;
  try {gl=gpuCanvas.getContext('webgl2',{alpha:true,premultipliedAlpha:false,antialias:false,preserveDrawingBuffer:true});}
  catch {} // Restricted browser: use the CPU renderer.
  let gpu=null,cpu=null,archives=null;
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
  // Geographic Sun direction is fixed to the approved presentation reference,
  // rather than following the frame count, terminal clock or simulated world.
  const angle=2*Math.PI/365*(172+(1-12)/24);
  const equation=229.18*(.000075+.001868*Math.cos(angle)-.032077*Math.sin(angle)-.014615*Math.cos(2*angle)-.040849*Math.sin(2*angle));
  const declination=.006918-.399912*Math.cos(angle)+.070257*Math.sin(angle)-.006758*Math.cos(2*angle)+.000907*Math.sin(2*angle)-.002697*Math.cos(3*angle)+.00148*Math.sin(3*angle);
  const radians=Math.PI/180;
  const sunLon=(165-equation/4)*radians;
  function initGPU(images){
    if(!gl||gl.isContextLost())return null;
    const max=gl.getParameter(gl.MAX_TEXTURE_SIZE);
    if(images.some(i=>i.naturalWidth>max||i.naturalHeight>max))return null;
    const vs=shader(gl.VERTEX_SHADER,vertex),fs=shader(gl.FRAGMENT_SHADER,fragment);
    if(!vs||!fs)return null;
    const program=gl.createProgram();
    gl.attachShader(program,vs);gl.attachShader(program,fs);gl.linkProgram(program);
    gl.deleteShader(vs);gl.deleteShader(fs);
    if(!gl.getProgramParameter(program,gl.LINK_STATUS))return null;
    gl.useProgram(program);
    const locate=n=>gl.getUniformLocation(program,n);
    gl.uniform1i(locate('uDay'),0);gl.uniform1i(locate('uNight'),1);
    gl.uniform2f(locate('uSun'),declination,sunLon);
    images.forEach(upload);
    return gl.getError()===gl.NO_ERROR?{
      size:locate('uSize'),camera:locate('uCamera'),zoom:locate('uZoom')
    }:null;
  }
  function initCPU(images){
    try {
      const textures=images.map((image,i)=>{
        const scratch=document.createElement('canvas');
        scratch.width=i===0?1536:1024;scratch.height=scratch.width/2;
        const context=scratch.getContext('2d',{willReadFrequently:true});
        if(!context)throw new Error('canvas unavailable');
        context.drawImage(image,0,0,scratch.width,scratch.height);
        return {data:context.getImageData(0,0,scratch.width,scratch.height).data,
          width:scratch.width,height:scratch.height};
      });
      const emitter=document.createElement('canvas'),ink=emitter.getContext('2d');
      return ink?{textures,emitter,ink}:null;
    } catch { return null; }
  }
  const sm=(x)=>{x=clamp(x,0,1);return x*x*(3-2*x);};
  const cobaltRamp=[[2,7,53],[3,8,82],[6,10,114],[12,20,143],[16,29,163],[25,87,187]];
  const shadingLUT=Float32Array.from({length:256},(_,i)=>(i/255)**2.18);
  function texOffset(tex,lat,lon){
    const q=lon/(2*Math.PI)+.5;
    return 4*(clamp(Math.floor((.5-lat/Math.PI)*tex.height),0,tex.height-1)*tex.width+
      Math.floor((q-Math.floor(q))*tex.width));
  }
  function cpuDraw(width,height){
    const {textures:[day,night],emitter,ink}=cpu;
    const ratio=Math.min(1,320/Math.max(width,height));
    const w=Math.max(1,Math.round(width*ratio)),h=Math.max(1,Math.round(height*ratio));
    if(emitter.width!==w||emitter.height!==h){
      emitter.width=w;emitter.height=h;cpu.pixels=null;
    }
    if(!cpu.pixels)cpu.pixels=ink.createImageData(w,h);
    const pix=cpu.pixels.data, radius=Math.min(w,h)*.45*zoom;
    const p=latitude*radians,l=longitude*radians,cp=Math.cos(p),sp=Math.sin(p);
    const sunP=Math.sin(declination),sunE=Math.cos(declination);
    for(let y=0,i=0;y<h;y++){
      const v=(h/2-y-.5)/radius,vv=v*v;
      for(let x=0;x<w;x++,i+=4){
        const u=(x+.5-w/2)/radius,q2=u*u+vv;
        if(q2>1.095){pix[i+3]=0;continue;}
        const z=Math.sqrt(Math.max(0,1-q2));
        const sinLat=clamp(v*cp+z*sp,-1,1);
        const lat=Math.asin(sinLat),lon=l+Math.atan2(u,z*cp-v*sp);
        const mu=sinLat*sunP+Math.sqrt(Math.max(0,1-sinLat*sinLat))*sunE*Math.cos(lon-sunLon);
        const side=.10+.90*sm((mu+.24)/1.02);
        if(q2>1){
          const fringe=(Math.sqrt(q2)-1)*radius,scale=Math.max(radius/410,.52);
          pix[i]=77;pix[i+1]=135;pix[i+2]=214;
          pix[i+3]=255*side*(.58*Math.exp(-fringe/(2*scale))+.125*Math.exp(-fringe/(8.7*scale)));
          continue;
        }
        const d=texOffset(day,lat,lon),n=texOffset(night,lat,lon);
        let r=day.data[d],g=day.data[d+1],b=day.data[d+2];
        const water=sm(((b-r)/255-.021)/.22)*sm(((b-g)/255+.038)/.16);
        const warm=sm(((r-b)/255-.03)/.29)*(1-sm((r/255-.62)/.35));
        r=shadingLUT[Math.round(r*(1-.24*water-.11*warm))];
        g=shadingLUT[Math.round(g*(1-.20*water))];
        b=shadingLUT[clamp(Math.round(b*(1-.045*water)+8.16*warm),0,255)];
        const exp=.010+.25*sm((mu+.018)/.57)+.69*Math.max(0,mu)**.62;
        const dens=clamp(((night.data[n]+night.data[n+1])/255-.095)/1.1,0,1);
        const city=(1-sm((Math.abs(lat)-1.10)/.20))*(1-sm((mu+.19)/.24))*
          (.034*sm(dens/.31)+.53*sm((dens-.12)/.72));
        r=r*exp*.987*(1-city)+.97*city;
        g=g*exp*1.011*(1-city)+.59*city;
        b=b*exp*1.034*(1-city)+.21*city;
        const limb=side*(1-z)**17,scatter=side*(1-z)**4.5;
        r=clamp(r+(1-r)*(.41*limb+.005*scatter),0,1)**(1/2.20);
        g=clamp(g+(1-g)*(.69*limb+.027*scatter),0,1)**(1/2.20);
        b=clamp(b+(1-b)*(.97*limb+.061*scatter),0,1)**(1/2.20);
        const strength=.99*sm((water-.16)/.71)*sm((b-r-.022)/.19)*
          (1-sm((r-.25)/.28))*(1-.94*sm((1-z-.66)/.34))*sm((b-.06)/.17)*
          (1-.48*sm((g-.45)/.49)*sm((b-.41)/.47));
        const c=clamp((.85*b+.15*g-.115)/.65,0,1)*5,idx=Math.min(4,Math.floor(c)),f=c-idx;
        const a=cobaltRamp[idx],j=cobaltRamp[idx+1],t=1-strength;
        pix[i]=255*r*t+strength*(a[0]+(j[0]-a[0])*f);
        pix[i+1]=255*g*t+strength*(a[1]+(j[1]-a[1])*f);
        pix[i+2]=255*b*t+strength*(a[2]+(j[2]-a[2])*f);
        pix[i+3]=255;
      }
    }
    ink.putImageData(cpu.pixels,0,0);
    return emitter;
  }
  function chooseRenderer(){
    try {gpu=initGPU(archives);} catch {gpu=null;}
    if(!gpu)cpu=initCPU(archives);
    ready=Boolean(gpu||cpu);
    if(ready){
      globe.dataset.celestialReady='true';
      globe.dataset.celestialRenderer=gpu?'webgl2':'canvas2d';
    } else {
      delete globe.dataset.celestialReady;delete globe.dataset.celestialRenderer;
    }
  }
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
  let twin=false,geography=null;
  const twinGrid=document.createElement('canvas'), twinGridInk=twinGrid.getContext('2d');
  function packVector(points){
    const xyz=new Float32Array(points.length*3);
    for(let i=0;i<points.length;i++)xyz.set(vector(points[i][1]*radians,points[i][0]*radians),i*3);
    return xyz;
  }
  function unpackTwin(raw){
    const bytes=atob(raw); let i=0;
    const int=()=>{let v=0,k=0,b;do{
      if(i>=bytes.length||k>27)throw new Error('Invalid geography');
      b=bytes.charCodeAt(i++);v|=(b&127)<<k;k+=7;
    }while(b&128);return v&1?-(v+1)/2:v/2;};
    const sets=Array.from({length:4},()=>Array.from({length:int()},()=>{
      let x=0,y=0;
      return packVector(Array.from({length:int()},()=>{x+=int();y+=int();return [x/10000,y/10000];}));
    }));
    if(i!==bytes.length)throw new Error('Invalid geography length');
    const grid=[];
    for(let y=-80;y<=80;y+=10)grid.push(packVector(Array.from({length:721},(_,j)=>[j/2-180,y])));
    for(let x=-180;x<180;x+=10)grid.push(packVector(Array.from({length:361},(_,j)=>[x,j/2-90])));
    return {sets,grid};
  }
  function drawTwin(w,h,scale){
    const c=output, g=twinGridInk;
    const r=Math.min(w,h)*.45*zoom,x0=w/2,y0=h/2;
    const p=latitude*radians,l=longitude*radians;
    const xe=-Math.sin(l),ye=Math.cos(l),xn=-Math.sin(p)*Math.cos(l),yn=-Math.sin(p)*Math.sin(l),zn=Math.cos(p);
    const [xf,yf,zf]=vector(p,l);
    const clipDepth=.007;
    function shape(ctx, group){
      ctx.beginPath();
      for(const path of group){
        let px=0,py=0,pz=-2;
        for(let i=0;i<path.length;i+=3){
          const a=path[i],b=path[i+1],k=path[i+2];
          const x=x0+r*(a*xe+b*ye),y=y0-r*(a*xn+b*yn+k*zn),z=a*xf+b*yf+k*zf;
          if(i===0){if(z>=clipDepth)ctx.moveTo(x,y);}
          else if(z>=clipDepth && pz>=clipDepth)ctx.lineTo(x,y);
          else if((z>=clipDepth)!==(pz>=clipDepth)){
            const tm=(clipDepth-pz)/(z-pz),cx=px+(x-px)*tm,cy=py+(y-py)*tm;
            if(z>=clipDepth){ctx.moveTo(cx,cy);ctx.lineTo(x,y);}
            else ctx.lineTo(cx,cy);
          }
          px=x;py=y;pz=z;
        }
      }
    }
    function disk(ctx){ctx.beginPath();ctx.arc(x0,y0,r,0,Math.PI*2);}
    const [outlines,borders,flagged,disputed]=geography.sets;
    c.clearRect(0,0,w,h);
    arcContext?.clearRect(0,0,lines.width,lines.height);
    const halo=c.createRadialGradient(x0,y0,r*.98,x0,y0,r*1.12);
    halo.addColorStop(0,'rgba(41,145,209,.30)');halo.addColorStop(.17,'rgba(41,145,209,.25)');halo.addColorStop(1,'rgba(19,101,183,0)');
    c.fillStyle=halo;c.fillRect(0,0,w,h);
    const ocean=c.createRadialGradient(x0-r*.38,y0-r*.37,r*.04,x0-r*.16,y0-r*.12,r*1.20);
    ocean.addColorStop(0,'#05293e');ocean.addColorStop(.66,'#041727');ocean.addColorStop(.92,'#0a2543');ocean.addColorStop(1,'#133954');
    disk(c);c.fillStyle=ocean;c.fill();
    c.save();disk(c);c.clip();
    if(g){
      if(twinGrid.width!==w)twinGrid.width=w;
      if(twinGrid.height!==h)twinGrid.height=h;
      g.clearRect(0,0,w,h);
      g.save();g.strokeStyle='rgba(31,169,230,.40)';g.lineWidth=Math.max(.65,.69*scale);
      g.setLineDash([3.5*scale,4*scale]);shape(g,geography.grid);g.stroke();
      g.globalCompositeOperation='destination-out';g.strokeStyle='#000';g.lineWidth=5.5*scale;g.setLineDash([]);
      shape(g,outlines);g.stroke();shape(g,borders);g.stroke();shape(g,flagged);g.stroke();shape(g,disputed);g.stroke();
      g.restore();c.drawImage(twinGrid,0,0);
    }
    c.lineJoin='round';c.lineWidth=Math.min(.85*scale,r*.0044);c.strokeStyle='#6de0f9';shape(c,outlines);c.stroke();
    c.strokeStyle='#3287b7';c.lineWidth=.7*scale;shape(c,borders);c.stroke();
    c.strokeStyle='#e6c7a4';c.lineWidth=.85*scale;c.setLineDash([3.5*scale,3.5*scale]);
    shape(c,flagged);c.stroke();shape(c,disputed);c.stroke();
    c.restore();disk(c);c.strokeStyle='#55c9ed';c.lineWidth=.85*scale;c.stroke();
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
    if(!ready||!active)return;
    const area=view.getBoundingClientRect();
    if(area.width<1||area.height<1)return;
    const scale=Math.min(window.devicePixelRatio||1,960/Math.max(area.width,area.height));
    const w=Math.max(1,Math.round(area.width*scale)),h=Math.max(1,Math.round(area.height*scale));
    if(planet.width!==w)planet.width=w;
    if(planet.height!==h)planet.height=h;
    if(twin){drawTwin(w,h,scale);return;}
    let image;
    if(gpu&&!gl.isContextLost()){
      if(gpuCanvas.width!==w)gpuCanvas.width=w;
      if(gpuCanvas.height!==h)gpuCanvas.height=h;
      gl.viewport(0,0,w,h);
      gl.uniform2f(gpu.size,w,h);gl.uniform2f(gpu.camera,latitude*radians,longitude*radians);
      gl.uniform1f(gpu.zoom,zoom);gl.drawArrays(gl.TRIANGLES,0,3);
      image=gpuCanvas;
    } else if(cpu)image=cpuDraw(w,h);
    if(image){
      output.clearRect(0,0,w,h);output.drawImage(image,0,0,w,h);drawArcs(w,h);
    }
  }
  function stop(){cancelAnimationFrame(frame);frame=0;last=0;}
  function animate(t){
    if(!active||manual||motion.matches||document.hidden){stop();return;}
    if(!last||t-last>=1000/(twin?12:gpu?28:12)){
      if(last)longitude=wrap(longitude+.844*Math.min(180,t-last)/1000);
      last=t;draw();
    }
    frame=requestAnimationFrame(animate);
  }
  function sync(){
    const layout=document.body.dataset.layout;
    active=ready&&visible&&!document.hidden&&(layout==='normal'||layout==='globe')&&globe.classList.contains('primary');
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
  if(typeof globalThis.HS_TWIN_GEOGRAPHY==='string'){
    const mode=button('デジタルツイン',()=>{
      if(!twin&&!geography){
        try {geography=unpackTwin(globalThis.HS_TWIN_GEOGRAPHY);}
        catch {mode.disabled=true;return;}
      }
      twin=!twin; mode.setAttribute('aria-pressed',String(twin));
      globe.dataset.celestialMode=twin?'twin':'real';
      caption.hidden=twin; twinCaption.hidden=!twin;
      // Do not call interact(): changing layers keeps the current camera and its motion.
      draw();
    });
    mode.setAttribute('aria-pressed','false');
  }
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
  gpuCanvas.addEventListener('webglcontextlost',()=>{
    if(!archives)return;
    gpu=null;
    if(!cpu)cpu=initCPU(archives);
    ready=Boolean(cpu);
    if(ready)globe.dataset.celestialRenderer='canvas2d';
    else {delete globe.dataset.celestialReady;delete globe.dataset.celestialRenderer;}
    sync();
  });
  const observer=new MutationObserver(sync);
  observer.observe(globe,{attributes:true,attributeFilter:['class']});
  observer.observe(document.body,{attributes:true,attributeFilter:['data-layout']});
  new ResizeObserver(draw).observe(view);
  new IntersectionObserver(([event])=>{visible=event.isIntersecting;sync();}).observe(globe);
  document.addEventListener('visibilitychange',sync);
  motion.addEventListener('change',()=>{if(motion.matches)stop();sync();});
  Promise.all([load('assets/globe-surface.webp'),load('assets/normal-night-2016.webp')]).then(images=>{
    archives=images;chooseRenderer();sync();stars?.redraw();
  }).catch(()=>{}); // Keep the existing accessible wireframe if local assets or WebGL fail.
})();
