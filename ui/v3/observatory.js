'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const names = {food:'食料', energy:'エネルギー'};
  const positions = [[12,12],[12,36],[12,60],[12,84],[88,84],[88,60],[88,36],[88,12]];
  let model, selected = null, selectedRoute = null;
  const el = (tag, text, cls) => {const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
  const svgEl = (tag, attrs) => {const n=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,String(v));return n;};
  const label = id => model.states.find(s=>s.id===id).label;
  function validate(m) {
    if(m.version!=='v3'||m.visual_baseline!=='candidate'||m.artifact_class!=='synthetic_baseline'||m.formal_worldline!==null||m.turn!==null||m.research_eligible!==false)throw Error('baseline contract');
    if(m.states.length!==8||new Set(m.states.map(s=>s.id)).size!==8||m.states.map(s=>s.label).join('')!=='ABCDEFGH')throw Error('state contract');
    for(const s of m.states)for(const r of m.resources){const v=s.resources[r.id];if(!v||![v.stock,v.demand,v.production_capacity].every(q=>Number.isSafeInteger(q)&&q>=0))throw Error('resource contract');}
    if(new Set(m.routes.map(r=>r.id)).size!==m.routes.length)throw Error('duplicate route');
    for(const r of m.routes)if(!m.states.some(s=>s.id===r.source)||!m.states.some(s=>s.id===r.target)||!Number.isSafeInteger(r.capacity)||r.capacity<0||!Number.isSafeInteger(r.delay)||r.delay<1)throw Error('route contract');
    for(const v of Object.values(m.measurements))if(v!==null)throw Error('not formal observations');
  }
  function routePath(r) {
    const a=positions[model.states.findIndex(s=>s.id===r.source)],b=positions[model.states.findIndex(s=>s.id===r.target)];
    const x1=a[0]*10,y1=a[1]*6.4,x2=b[0]*10,y2=b[1]*6.4;
    let cx,cy;
    if((x1<500)===(x2<500)){cx=x1<500?70:930;cy=(y1+y2)/2;}
    else{cx=500;cy=(y1+y2)/2<320?-80:710;}
    return `M ${x1} ${y1} Q ${cx} ${cy} ${x2} ${y2}`;
  }
  function drawWorld() {
    const maxCapacity=Math.max(1,...model.routes.map(r=>r.capacity));
    for(const r of model.routes){const p=svgEl('path',{d:routePath(r),class:'route','data-route':r.id,'stroke-width':.6+1.8*r.capacity/maxCapacity,'marker-end':'url(#route-tip)'});$('route-lines').append(p);}
    model.states.forEach((s,i)=>{
      const button=el('button',undefined,'state-node');button.type='button';button.dataset.state=s.id;button.style.left=positions[i][0]+'%';button.style.top=positions[i][1]+'%';button.setAttribute('aria-pressed','false');
      button.setAttribute('aria-label',`${s.label}国。初期食料 ${s.resources.food.stock}、初期エネルギー ${s.resources.energy.stock}。国家詳細`);
      button.append(el('span',s.label+'国','state-letter'));
      for(const r of model.resources){const row=el('span',undefined,'mini-resource '+r.id);row.append(el('small',names[r.id]));const track=el('span',undefined,'track');const bar=el('i');bar.style.width=(model.scales[r.id]?100*s.resources[r.id].stock/model.scales[r.id]:0)+'%';bar.dataset.stock=s.resources[r.id].stock;bar.dataset.resource=r.id;track.append(bar);row.append(track,el('strong',String(s.resources[r.id].stock)));button.append(row);}
      button.addEventListener('click',()=>select(s.id));
      button.addEventListener('keydown',e=>{if(['ArrowRight','ArrowDown','ArrowLeft','ArrowUp'].includes(e.key)){e.preventDefault();const next=(i+(['ArrowRight','ArrowDown'].includes(e.key)?1:7))%8;document.querySelectorAll('.state-node')[next].focus();}if(e.key==='Escape')select(null);});
      $('state-nodes').append(button);
    });
    $('route-count').textContent=`${model.states.length} STATES · ${model.routes.length} ROUTES`;
  }
  function highlight(){
    for(const p of document.querySelectorAll('.route')){const r=model.routes.find(r=>r.id===p.dataset.route);const related=r.source===selected||r.target===selected;p.classList.toggle('related',!!selected&&related);p.classList.toggle('faded',!!selected&&!related);p.classList.toggle('focused',r.id===selectedRoute);}
    for(const b of document.querySelectorAll('.state-node'))b.setAttribute('aria-pressed',String(b.dataset.state===selected));
  }
  function select(id) {
    selected=id;selectedRoute=null;highlight();
    const s=model.states.find(s=>s.id===id);$('selected-label').textContent=s?s.label:'—';
    $('resource-details').replaceChildren();$('route-details').replaceChildren();$('production-dependencies').replaceChildren();
    if(!s){$('resource-details').append(el('p','8国家の合成初期在庫。食料・エネルギーは有限。','muted'));$('connection-context').textContent='全18経路の存在構造。実行・着荷は未観測。';}
    else{
      for(const r of model.resources){const v=s.resources[r.id];const row=el('div',undefined,'resource-row '+r.id);row.append(el('strong',names[r.id]));for(const [title,key] of [['初期在庫','stock'],['必須需要 / TURN','demand'],['生産能力 / TURN','production_capacity']]){const field=el('div');field.append(el('span',title),el('b',String(v[key])));row.append(field);}row.dataset.resource=r.id;$('resource-details').append(row);}
      $('resource-details').append(el('p','単位：food_unit / energy_unit。生産能力は在庫ではない。','unit-note'));
      $('connection-context').textContent=`${s.label}国に接続する構造。容量は共有制約を持つ。`;
    }
    const routes=model.routes.filter(r=>!id||r.source===id||r.target===id);
    for(const r of routes){const row=el('button',undefined,'route-row');row.type='button';row.dataset.route=r.id;row.setAttribute('aria-pressed','false');row.append(el('span',`${label(r.source)} → ${label(r.target)}`),el('small',r.resources.map(x=>names[x]).join(' / ')),el('small',`容量 ${r.capacity} · ${r.delay} TURN`));row.title=`${r.id} / ${r.shared_group} / transport_unit_per_turn`;row.addEventListener('click',()=>{selectedRoute=selectedRoute===r.id?null:r.id;highlight();for(const b of document.querySelectorAll('.route-row'))b.setAttribute('aria-pressed',String(b.dataset.route===selectedRoute));});$('route-details').append(row);}
    for(const d of model.production_dependencies.filter(d=>!id||d.producer_state===id))$('production-dependencies').append(el('p',`${label(d.producer_state)}国：${names[d.input_resource]} ${d.required_input} → ${names[d.output_resource]} ${d.output_batch} ／ ${d.output_delay} TURN後`,'dependency'));
    if(!$('production-dependencies').children.length)$('production-dependencies').append(el('p','定義された投入依存なし。','muted'));
  }
  function evidence(){
    for(const [key,source] of Object.entries(model.provenance)){const box=el('div',undefined,'evidence-source');const link=el('a',key==='baseline'?'合成基準世界':'合成ネットワーク');link.href=source.path;box.append(link,el('code','SHA256 '+source.file_sha256));$('source-evidence').append(box);}
    const mapping=el('details');mapping.append(el('summary','国家識別と原本対応'));mapping.append(el('p',model.states.map(s=>`${s.label} = ${s.id}`).join(' ／ ')));$('source-evidence').append(mapping);
  }
  $('clear-selection').addEventListener('click',()=>select(null));
  fetch('ui/v3/baseline.json',{cache:'no-cache'}).then(r=>{if(!r.ok)throw Error('missing baseline');return r.json();}).then(m=>{validate(m);model=m;drawWorld();evidence();select(model.states[0].id);window.V3Candidate=Object.freeze({ready:true,artifactClass:m.artifact_class,visualBaseline:'candidate'});}).catch(()=>{$('load-error').hidden=false;$('load-error').textContent='構造データを検証できません。研究値は表示していません。';$('route-count').textContent='構造データ未検証';$('clear-selection').disabled=true;});
})();
