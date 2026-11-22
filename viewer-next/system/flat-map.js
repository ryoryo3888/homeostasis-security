"use strict";
(() => {
  const map=document.getElementById("map");
  if (!map) return;
  const element=(tag,cls,text)=>{
    const item=document.createElement(tag);
    if(cls)item.className=cls;
    if(text)item.textContent=text;
    return item;
  };
  const stage=element("section","hs-flat-map"), viewport=element("div","hs-flat-viewport");
  const canvas=element("canvas","hs-flat-canvas");
  const modes=element("div","hs-flat-modes"), operations=element("div","hs-flat-operations");
  const viewLabel=element("div","hs-flat-status"), attribution=element("p","hs-flat-source");
  const realNote=element("span",null,"｜過去の衛星合成。雲は現在の気象ではありません。");
  const twinNote=element("span",null,"｜海岸線・国境の目安と経緯線。観測・演算結果ではありません。");
  const nasa=element("a",null,"NASA/GSFC SVS");
  nasa.href="https://svs.gsfc.nasa.gov/3615";
  const naturalEarth=element("a",null,"Natural Earth 1:50m");
  naturalEarth.href="https://www.naturalearthdata.com/about/terms-of-use/";
  modes.setAttribute("role","group");modes.setAttribute("aria-label","世界地図の表示モード");
  operations.setAttribute("role","group");operations.setAttribute("aria-label","地図の移動・縮尺");
  viewLabel.setAttribute("role","status");
  canvas.tabIndex=0;
  canvas.setAttribute("aria-label","世界地図。矢印で移動、プラスとマイナスで拡大縮小できます。");
  viewport.append(canvas);
  stage.setAttribute("aria-label","インタラクティブな世界地図");
  stage.append(modes,viewport,operations,viewLabel,attribution);
  map.prepend(stage);

  const ink=canvas.getContext("2d");
  if(!ink)return;
  const home={lon:150,lat:0,zoom:1}, view={...home};
  const normalize=x=>((x+180)%360+360)%360-180;
  const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
  const photo=new Image();
  let photoReady=false,paths,styledPhoto,captionKey,userMode=false,mode="real",bounds=true,grid=true,names=false,queued=0,drag;
  const coast=new Path2D();
  const geography=()=>{
    const bytes=atob(globalThis.HS_TWIN_GEOGRAPHY);let i=0;
    const read=()=>{
      let v=0,b,s=0;
      do {if(i>=bytes.length||s>27)throw new Error("Invalid geography");
        b=bytes.charCodeAt(i++);v|=(b&127)<<s;s+=7;
      } while(b&128);
      return v&1?-(v+1)/2:v/2;
    };
    // The published Natural Earth bundle already splits land rings at ±180°.
    // Keep those rings intact for fill. Split line-only geometry on discontinuities.
    const groups=Array.from({length:4},(_,k)=>{
      const p=new Path2D();
      const m=read();
      if(m<1||m>10000)throw new Error("Invalid geography groups");
      for(let j=0;j<m;j++){
        const count=read();
        if(count<2||count>150000)throw new Error("Invalid geography path");
        let x=0,y=0;
        for(let q=0;q<count;q++){
          const priorX=x,dx=read();x+=dx;y+=read();
          if(Math.abs(x)>1800000||Math.abs(y)>900000||(k===0&&q&&Math.abs(dx)>1800000))throw new Error("Invalid geography point");
          if(q===0||Math.abs(dx)>1800000)p.moveTo(x/10000,-y/10000);
          else p.lineTo(x/10000,-y/10000);
          if(k===0){
            if(q===0||(x===priorX&&Math.abs(x)===1800000))coast.moveTo(x/10000,-y/10000);
            else coast.lineTo(x/10000,-y/10000);
          }
        }
        if(k===0)p.closePath();
      }
      return p;
    });
    if(i!==bytes.length)throw new Error("Invalid geography length");
    return groups;
  };
  const graticule=new Path2D();
  for(let x=-180;x<180;x+=15){graticule.moveTo(x,-90);graticule.lineTo(x,90);}
  for(let y=-75;y<=75;y+=15){graticule.moveTo(-180,y);graticule.lineTo(180,y);}
  // Cartographic reference labels, not alerts or samples. Coordinates do not change between layers.
  const labelPoints=[
    ["日本",137,37],["中国",102,34],["韓国",127.8,36],["インド",79,22],
    ["オーストラリア",134,-26],["ニュージーランド",173,-41],["ロシア",95,61],
    ["カナダ",-104,56],["米国",-100,37],["メキシコ",-102,23],["ブラジル",-51,-11],
    ["アルゼンチン",-65,-36],["英国",-2,54.6],["フランス",2,46.7],["ドイツ",10.5,51],
    ["エジプト",29,26],["南アフリカ",24,-31],["インドネシア",117,-3],
    ["太平洋",175,7],["インド洋",82,-23],["大西洋",-42,-11]
  ];
  const addButton=(container,text,onClick)=>{
    const b=element("button",null,text);b.type="button";b.addEventListener("click",onClick);container.append(b);return b;
  };
  const real=addButton(modes,"リアル",()=>setMode("real"));
  const twin=addButton(modes,"デジタルツイン",()=>setMode("twin"));
  const goHome=()=>{Object.assign(view,home);update();};
  addButton(operations,"東へ",()=>pan(30/view.zoom,0));
  addButton(operations,"西へ",()=>pan(-30/view.zoom,0));
  const north=addButton(operations,"北へ",()=>pan(0,24/view.zoom));
  const south=addButton(operations,"南へ",()=>pan(0,-24/view.zoom));
  const zoomIn=addButton(operations,"拡大",()=>zoom(1.5));
  const zoomOut=addButton(operations,"縮小",()=>zoom(1/1.5));
  addButton(operations,"全体",goHome);
  addButton(operations,"日本周辺",()=>{Object.assign(view,{lon:136,lat:36,zoom:6});update();});
  const layerButtons=element("div","hs-flat-layers");
  layerButtons.setAttribute("role","group");layerButtons.setAttribute("aria-label","参照レイヤー");
  stage.insertBefore(layerButtons,viewLabel);
  const boundaries=addButton(layerButtons,"国境",()=>{bounds=!bounds;update();});
  const gridToggle=addButton(layerButtons,"経緯線",()=>{grid=!grid;update();});
  const placeNames=addButton(layerButtons,"地名（主要）",()=>{names=!names;update();});
  const visible=()=>document.body.dataset.layout==="map"&&map.classList.contains("primary");
  function setMode(next){
    if(next==="twin"&&!paths||next==="real"&&!photoReady)return;
    userMode=true;mode=next;update();
  }
  function constrainLat(){
    view.lat=clamp(view.lat,-90+90/view.zoom,90-90/view.zoom);
  }
  function pan(horizontal,vertical){
    view.lon=normalize(view.lon+horizontal);view.lat+=vertical;constrainLat();update();
  }
  function zoom(ratio){
    view.zoom=clamp(view.zoom*ratio,1,8);constrainLat();update();
  }
  function update(){
    real.disabled=!photoReady;twin.disabled=!paths;
    const analysis=mode==="twin";
    real.setAttribute("aria-pressed",String(!analysis));twin.setAttribute("aria-pressed",String(analysis));
    for(const [button,value] of [[boundaries,bounds],[gridToggle,grid],[placeNames,names]])button.setAttribute("aria-pressed",String(value));
    boundaries.disabled=gridToggle.disabled=!paths;
    zoomIn.disabled=view.zoom>=8;zoomOut.disabled=view.zoom<=1;
    north.disabled=view.lat>=90-90/view.zoom;south.disabled=view.lat<=-90+90/view.zoom;
    map.dataset.flatMode=mode;map.dataset.flatCenter=view.lon.toFixed(3)+","+view.lat.toFixed(3);map.dataset.flatZoom=view.zoom.toFixed(3);
    const format=(n,negative,positive)=>n===0?"0°":(n<0?negative:positive)+Math.abs(n).toFixed(1)+"°";
    viewLabel.textContent="中心 "+format(view.lat,"南緯","北緯")+"・"+format(view.lon,"西経","東経")+" ｜ "+view.zoom.toFixed(1)+" 倍 ｜ 観測レイヤー：未取得";
    const nextCaptionKey=[mode,!!paths,bounds,grid].join();
    if(captionKey!==nextCaptionKey){
      captionKey=nextCaptionKey;
      attribution.replaceChildren(
        ...(analysis?[naturalEarth,twinNote]:[nasa,realNote]),
        ...(paths&&bounds?[document.createTextNode(" 国境は参照用。暖色破線：係争・管理線など。")]:[])
      );
      if(!analysis&&paths&&(bounds||grid))attribution.append(" 線：",naturalEarth);
    }
    if(!queued)queued=requestAnimationFrame(draw);
  }
  function draw(){
    queued=0;
    if(!visible()||!photoReady&&!paths)return;
    const rect=canvas.getBoundingClientRect();
    if(rect.width<1)return;
    const density=Math.min(devicePixelRatio||1,2160/rect.width,2);
    const w=Math.round(rect.width*density),h=Math.round(rect.height*density);
    if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;}
    const unit=w*view.zoom/360,x0=w*.5-view.lon*unit,y0=h*.5+view.lat*unit;
    const analysis=mode==="twin";
    ink.setTransform(1,0,0,1,0,0);
    ink.fillStyle=analysis?"#07101d":"#030a1a";ink.fillRect(0,0,w,h);
    const first=Math.floor((view.lon-180/view.zoom+180)/360),last=Math.floor((view.lon+180/view.zoom+180)/360);
    if(!analysis&&photoReady){
      ink.imageSmoothingQuality="high";
      for(let k=first;k<=last;k++){
        const x=x0+(360*k-180)*unit, xEnd=x0+(360*k+180)*unit;
        ink.drawImage(styledPhoto||photo,Math.round(x),y0-90*unit,Math.round(xEnd)-Math.round(x),180*unit);
      }
    }
    if(analysis){
      const water=ink.createLinearGradient(0,0,0,h);
      water.addColorStop(0,"#081a35");water.addColorStop(.6,"#030e24");water.addColorStop(1,"#060d1a");
      ink.fillStyle=water;ink.fillRect(0,0,w,h);
    }
    const withTiles=fn=>{
      for(let k=first;k<=last;k++){
        ink.setTransform(unit,0,0,unit,x0+360*k*unit,y0);
        fn();
      }
    };
    if(paths){
      ink.lineJoin="round";ink.lineCap="round";
      const brush=(path,paint,width,dash)=>{
        ink.strokeStyle=paint;ink.lineWidth=width*density/unit;ink.setLineDash(dash?dash.map(v=>v*density/unit):[]);
        ink.stroke(path);
      };
      if(analysis){
        withTiles(()=>{
          ink.fillStyle="#103050";ink.fill(paths[0],"evenodd");
          brush(coast,"#79b6df",.72);
        });
      }
      withTiles(()=>{
        if(grid)brush(graticule,analysis?"#4ec8f761":"#c1eaff46",.6,[2,4]);
        if(bounds){
          brush(paths[1],analysis?"#86d9f7":"#d4edfbad",.62);
          brush(paths[2],"#f1cba4",.72,[3,2.8]);
          brush(paths[3],"#f1cba4",.72,[3,2.8]);
        }
      });
    }
    ink.setTransform(1,0,0,1,0,0);ink.setLineDash([]);
    if(names){
      const used=[];
      ink.font=(Math.max(11,Math.min(14,rect.width*.025))*density)+"px sans-serif";
      ink.textBaseline="middle";ink.textAlign="center";
      for(const [name,lon,lat] of labelPoints){
        const xx=w*.5+normalize(lon-view.lon)*unit,yy=y0-lat*unit;
        const rw=ink.measureText(name).width/2+4*density,rh=9*density;
        if(xx-rw<0||xx+rw>w||yy-rh<0||yy+rh>h||used.some(([px,py,pw])=>Math.abs(px-xx)<pw+rw&&Math.abs(py-yy)<rh*2))continue;
        used.push([xx,yy,rw]);ink.lineWidth=3*density;ink.strokeStyle="#031022";ink.fillStyle="#f1f8ff";
        ink.strokeText(name,xx,yy);ink.fillText(name,xx,yy);
      }
    }
  }
  canvas.addEventListener("pointerdown",e=>{
    if(e.button!==0||!e.isPrimary)return;
    drag={id:e.pointerId,x:e.clientX,y:e.clientY,committed:e.pointerType!=="touch"};
    if(drag.committed)canvas.setPointerCapture(e.pointerId);
  });
  canvas.addEventListener("pointermove",e=>{
    if(!drag||drag.id!==e.pointerId)return;
    const dx=e.clientX-drag.x,dy=e.clientY-drag.y;
    if(!drag.committed){
      if(Math.abs(dy)>7&&Math.abs(dy)>Math.abs(dx)){drag=null;return;}
      if(Math.abs(dx)<7||Math.abs(dx)<=Math.abs(dy))return;
      drag.committed=true;canvas.setPointerCapture(e.pointerId);
    }
    const deg=360/(canvas.clientWidth*view.zoom);if(!Number.isFinite(deg))return;
    drag.x=e.clientX;drag.y=e.clientY;
    pan(-dx*deg,dy*deg);
  });
  for(const type of ["pointercancel","pointerup","lostpointercapture"])canvas.addEventListener(type,e=>{if(drag?.id===e.pointerId)drag=null;});
  canvas.addEventListener("keydown",e=>{
    const d=12/view.zoom,dirs={ArrowLeft:[-d,0],ArrowRight:[d,0],ArrowUp:[0,d],ArrowDown:[0,-d]};
    if(dirs[e.key]){e.preventDefault();pan(...dirs[e.key]);}
    if(["-","+","="].includes(e.key)){e.preventDefault();zoom(e.key==="-"?1/1.5:1.5);}
    if(e.key==="Home"){e.preventDefault();goHome();}
  });
  function prepareColor(){
    if(styledPhoto||!photoReady||!paths)return;
    const surface=document.createElement("canvas");surface.width=photo.naturalWidth;surface.height=photo.naturalHeight;
    const pixels=surface.getContext("2d");
    if(!pixels||!("filter" in pixels))return;
    pixels.filter="saturate(1.10) contrast(1.06)";
    pixels.drawImage(photo,0,0);
    const oceanMask=new Path2D();oceanMask.rect(-180,-90,360,180);oceanMask.addPath(paths[0]);
    // Shade only geography-backed ocean in the palette of the globe. Never classify land from RGB.
    const unit=surface.width/360;
    pixels.setTransform(unit,0,0,unit,surface.width*.5,surface.height*.5);
    pixels.clip(oceanMask,"evenodd");
    pixels.setTransform(1,0,0,1,0,0);
    pixels.filter="hue-rotate(23deg) saturate(1.22) contrast(1.11)";
    pixels.drawImage(photo,0,0);
    styledPhoto=surface;
  }
  // Data and media are existing local assets; neither presentation mode fetches observations.
  const activate=()=>{
    if(!visible())return;
    if(!paths){try{paths=geography();}catch{paths=null;}}
    try{prepareColor();}catch{ /* Keep the georeferenced source if color processing is unavailable. */ }
    if(photoReady||paths){
      if(!photoReady)mode="twin";
      map.dataset.flatReady="true";
    }
    update();
  };
  photo.onload=()=>{photoReady=photo.naturalWidth===photo.naturalHeight*2;if(photoReady){if(!userMode)mode="real";activate();}};
  photo.src="assets/globe-surface.webp";
  const watcher=new MutationObserver(activate);
  watcher.observe(map,{attributes:true,attributeFilter:["class"]});
  watcher.observe(document.body,{attributes:true,attributeFilter:["data-layout"]});
  new ResizeObserver(()=>{if(visible()&&!queued)queued=requestAnimationFrame(draw);}).observe(canvas);
  activate();
})();
