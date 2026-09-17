import {METRICS, RESOURCE_LABELS, format, projectWorldline, summarizeFlows, discoverMoments} from './view-model.js';

const $ = selector => document.querySelector(selector);
const escape = value => String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const json = value => escape(JSON.stringify(value, null, 2));
const label = resource => RESOURCE_LABELS[resource] ?? resource;
const sourceName = id => id === 'world_pool' ? 'WORLD POOL' : id;
const state = {index:0, lens:'conditions', resource:'food', extra:''};
let model, config;
const current = () => model.turns[state.index];
const coreMetrics = ['global_homeostasis','international_trust','conflict_load'];

function renderTrajectory() {
  const geometry = {width:840, height:295, left:34, right:25, top:20, bottom:35};
  const {width,height,left,right,top,bottom} = geometry;
  const x = index => left + index * (width-left-right) / Math.max(1, model.turns.length-1);
  const y = value => height-bottom-value/100*(height-top-bottom);
  const metrics = [...coreMetrics, ...(state.extra ? [state.extra] : [])];
  const grid = [0,50,100].map(value => `<line x1="${left}" x2="${width-right}" y1="${y(value)}" y2="${y(value)}" stroke="#354346" stroke-width=".7"/><text x="0" y="${y(value)+4}">${value}</text>`).join('');
  const paths = metrics.map(key => {
    const points = model.turns.map((turn,index) => `${x(index)},${y(turn.world[key])}`).join(' ');
    const circles = model.turns.map((turn,index) => `<circle cx="${x(index)}" cy="${y(turn.world[key])}" r="${index===state.index?4:2.5}" fill="${METRICS[key].color}"><title>TURN ${turn.number} ${METRICS[key].label}: ${turn.world[key]}</title></circle>`).join('');
    return `<polyline points="${points}" fill="none" stroke="${METRICS[key].color}" stroke-width="${key==='global_homeostasis'?2:1.25}" stroke-dasharray="${key==='international_trust'?'7 3':key==='conflict_load'?'2 3':'none'}"/>${circles}`;
  }).join('');
  const markers = model.turns.map((turn,index) => `<g role="button" tabindex="0" data-turn="${index}" aria-label="TURN ${turn.number}: ${escape(turn.event)}"><rect x="${x(index)-14}" y="${height-27}" width="28" height="27" fill="transparent"/><text x="${x(index)}" y="${height-9}" text-anchor="middle">${String(turn.number).padStart(2,'0')}</text></g>`).join('');
  $('#trajectory').innerHTML = `<svg viewBox="0 0 ${width} ${height}" aria-label="世界状態の軌跡。共通尺度0から100、観測点はTURNごとの値。">${grid}<line x1="${x(state.index)}" x2="${x(state.index)}" y1="${top}" y2="${height-bottom}" stroke="#dfc69c" stroke-opacity=".4"/>${paths}${markers}</svg>`;
  bindTurnChoices($('#trajectory'));
  $('#metric-legend').innerHTML = metrics.map(key => `<span style="--color:${METRICS[key].color}"><i aria-hidden="true"></i>${METRICS[key].label}</span>`).join('');
  const turn = current();
  $('#turn-number').textContent = String(turn.number).padStart(2,'0');
  $('#event-title').textContent = turn.event;
  $('#current-metrics').innerHTML = coreMetrics.map(key => `<div class="metric-readout ${key==='global_homeostasis'?'h':''}">${key==='global_homeostasis'?`<svg viewBox="0 0 50 50" aria-hidden="true"><circle cx="25" cy="25" r="23" fill="none" stroke="#354346"/><circle cx="25" cy="25" r="${23*Math.sqrt(turn.world[key]/100)}" fill="#dfc69c35" stroke="#dfc69c"/></svg>`:''}<div><small>${METRICS[key].label}</small><strong style="color:${METRICS[key].color}">${format(turn.world[key])}</strong></div></div>`).join('');
  $('#turn-buttons').style.gridTemplateColumns = `repeat(${model.turns.length},1fr)`;
  $('#turn-buttons').innerHTML = model.turns.map((turn,index) => `<button data-turn="${index}" aria-current="${index===state.index}" aria-label="TURN ${turn.number}を観測"><small>T </small><span>${String(turn.number).padStart(2,'0')}</span></button>`).join('');
  bindTurnChoices($('#turn-buttons'));
  $('#previous').disabled = state.index === 0;
  $('#next').disabled = state.index === model.turns.length-1;
}

function renderNetwork() {
  const turn = current();
  const geometry = {width:640, height:500, cx:320, cy:250, radius:185};
  const positions = Object.fromEntries(model.ids.map((id,index) => {
    const angle = -Math.PI/2 + index/model.ids.length*Math.PI*2;
    return [id, {x:geometry.cx+Math.cos(angle)*geometry.radius,y:geometry.cy+Math.sin(angle)*geometry.radius}];
  }));
  const lines = turn.edges.map(edge => {
    const a=positions[edge.dependent], b=positions[edge.required];
    const dx=b.x-a.x,dy=b.y-a.y,distance=Math.hypot(dx,dy), inset=42;
    if (!distance) return `<path d="M ${a.x-25} ${a.y-24} C ${a.x-95} ${a.y-95}, ${a.x+95} ${a.y-95}, ${a.x+25} ${a.y-24}" fill="none" stroke="#8bbfba" marker-end="url(#arrow)"><title>${escape(edge.dependent)}: 自己条件</title></path>`;
    return `<line x1="${a.x+dx/distance*inset}" y1="${a.y+dy/distance*inset}" x2="${b.x-dx/distance*inset}" y2="${b.y-dy/distance*inset}" stroke="#8bbfba" stroke-opacity=".65" stroke-width="1" marker-end="url(#arrow)"><title>${escape(edge.dependent)} → ${escape(edge.required)}: 参加条件</title></line>`;
  }).join('');
  $('#network').innerHTML = `<svg viewBox="0 0 640 500" role="img" aria-label="TURN ${turn.number}の条件依存グラフ。国家ボタンから詳細を確認できます。"><defs><marker id="arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0 L8 4 L0 8" fill="none" stroke="#8bbfba"/></marker></defs>${lines}<text x="320" y="245" text-anchor="middle" style="font-size:10px;letter-spacing:2px">TURN ${String(turn.number).padStart(2,'0')}</text><text x="320" y="266" text-anchor="middle" style="font-size:10px">${turn.edges.length} dependencies</text></svg>` + turn.agents.map(agent => `<button class="node ${agent.participates?'':'unsatisfied'}" data-agent="${escape(agent.id)}" style="left:${positions[agent.id].x/640*100}%;top:${positions[agent.id].y/500*100}%" aria-label="${escape(agent.id)} ${escape(agent.archetype)} ${agent.participates?'条件参加':'条件不成立'}の判断"><strong>${escape(agent.id)}</strong><small>${agent.participates?escape(agent.archetype):'× 条件不成立'}</small></button>`).join('');
  bindAgents($('#network'));
  $('#network-summary').textContent = `条件参加 ${turn.agents.filter(a=>a.participates).length} / ${turn.agents.length}　・　依存 ${turn.edges.length}本`;
}

function renderFlows() {
  const turn = current(), summary = summarizeFlows(turn,state.resource);
  const scale = Math.max(1,...summary.flows.map(flow=>flow.requested));
  $('#flow-totals').innerHTML = [['要求',summary.requested],['実現',summary.realized],['未達',summary.unmet]].map(([name,value])=>`<div><span>${name} / ${escape(label(state.resource))}</span><strong>${format(value)}</strong></div>`).join('');
  $('#flows').innerHTML = summary.flows.length ? summary.flows.map(flow => `<button class="flow-row" data-agent="${escape(flow.agent_id)}" aria-label="${escape(flow.agent_id)}の${escape(label(flow.resource))}、要求${format(flow.requested)}、実現${format(flow.realized)}、未達${format(flow.unmet)}の証拠"><span class="flow-label">${escape(sourceName(flow.source))} → ${escape(sourceName(flow.target))}<small>要求者 ${escape(flow.agent_id)}</small></span><span class="flow-track" aria-hidden="true"><span class="flow-request" style="width:${flow.requested/scale*100}%"><i class="flow-real" style="width:${flow.requested?flow.realized/flow.requested*100:0}%"></i><i class="flow-unmet" style="width:${flow.requested?flow.unmet/flow.requested*100:0}%"></i></span></span><span class="flow-number">${format(flow.realized)} / ${format(flow.requested)}<small>未達 ${format(flow.unmet)}</small></span></button>`).join('') : '<p class="subtle">このTURNにこの資源のatomic移転記録はありません。条件不成立の選択は「条件」から確認できます。</p>';
  bindAgents($('#flows'));
  $('#pools').innerHTML = model.resources.map(resource => `<button class="pool" data-resource="${escape(resource)}" aria-label="${escape(label(resource))} pool 開始${format(turn.openingPool[resource])}、決済後${format(turn.pool[resource])}。この資源を見る"><label>${escape(label(resource))}</label><span class="pool-bar" aria-hidden="true"><i style="width:${turn.pool[resource]}%"></i><b style="left:${turn.openingPool[resource]}%"></b></span><p>${format(turn.openingPool[resource])} → ${format(turn.pool[resource])}</p></button>`).join('');
  $('#pools').querySelectorAll('[data-resource]').forEach(button => button.addEventListener('click',()=>{state.resource=button.dataset.resource;$('#resource-select').value=state.resource;renderFlows();}));
}

function renderRecovery() {
  const maxRecovery = Math.max(1,...model.turns.map(turn=>turn.reconstruction.recovered));
  $('#recovery').innerHTML = `<div class="recovery-grid">${model.turns.map((turn,index)=>{const r=turn.reconstruction;return `<button class="recovery-column" data-turn="${index}" aria-current="${index===state.index}" aria-label="TURN ${turn.number} 残存損失${format(r.after)} tons、回復${format(r.recovered)} tons"><span class="scar" aria-hidden="true"><span style="height:${model.initialDamage?r.after/model.initialDamage*100:0}%"></span></span><b>${String(turn.number).padStart(2,'0')}</b><small>${format(r.after)} t</small><span class="recovery-bar" style="width:${r.recovered/maxRecovery*100}%" aria-hidden="true"><i style="width:${r.recovered?r.domestic_recovery/r.recovered*100:0}%"></i><i style="width:${r.recovered?r.external_support/r.recovered*100:0}%"></i></span></button>`;}).join('')}</div><div class="legend"><span style="--color:#8bbfba"><i></i>国内回復</span><span style="--color:#dfc69c"><i></i>外部支援による回復</span></div><div class="recovery-detail">${[['残存損失',current().reconstruction.after],['このTURNの回復',current().reconstruction.recovered],['国内',current().reconstruction.domestic_recovery],['外部',current().reconstruction.external_support]].map(([key,value])=>`<div><span>${key} / tons</span><strong>${format(value)}</strong></div>`).join('')}</div>`;
  bindTurnChoices($('#recovery'));
}

function renderResearchDepth() {
  const turn = current();
  $('#numeric-state').innerHTML = `<p>TURN ${turn.number}。モデル内の0〜100指標です。選択円の面積はHomeostasis / 100。数値は小数3桁表示、出典JSONは元の精度を保持します。</p><table><thead><tr><th>指標</th><th>値</th></tr></thead><tbody>${[...Object.entries(METRICS).map(([key,meta])=>[meta.label,turn.world[key]]),['National Sovereignty',turn.sovereignty]].map(([name,value])=>`<tr><th>${name}</th><td>${format(value)}</td></tr>`).join('')}</tbody></table><p class="source-links"><a href="${escape(config.report)}">全TURNの研究解析 ↗</a> · <a href="${escape(model.source)}">timeline JSON ↗</a></p>`;
  $('#narratives').innerHTML = `<h3>Coordinator / ${escape(turn.proposal.proposal_type)}</h3><p>${escape(turn.proposal.reason)}</p><p>要求：${escape(turn.proposal.requested_action)}</p><h3>Evaluator / 公開評価</h3><p>${escape(turn.evaluator.assessment)}</p><p class="subtle">評価文はモデルの解釈です。正式指標を変更しません。提案・公開理由と、実際のaction tupleは同義ではありません。</p>`;
  $('#event-evidence').innerHTML = `<p>現在のevent: ${escape(turn.event)}</p><p>前TURNのworld・action・historyから候補を生成し、直近2 eventを除外して最高順位を選択。すべて除外なら最高順位へ戻ります。TURN1のみ固定の初期条件です。</p><pre>${json(turn.derivation)}</pre><code>${escape(turn.evidence.pointer)}/event_derivation</code>`;
}

function openAgent(id) {
  const turn=current(), agent=turn.agents.find(a=>a.id===id);
  if (!agent) return;
  const response=agent.response,p=agent.action.parameters;
  const requested=agent.flows.length?agent.flows.reduce((sum,f)=>sum+f.requested,0):null;
  const realized=agent.flows.length?agent.flows.reduce((sum,f)=>sum+f.realized,0):null;
  const unmet=agent.flows.length?agent.flows.reduce((sum,f)=>sum+f.unmet,0):null;
  $('#evidence-content').innerHTML = `<h2 id="evidence-title">${escape(id)}<small>TURN ${turn.number} · ${escape(agent.archetype)}</small></h2><span class="badge">${escape(response.response_id)}</span><span class="badge ${agent.participates?'':'unsatisfied-text'}">${agent.participates?'条件参加':'× 条件不成立'}</span><p>${escape(response.reason)}</p><h3>${escape(response.choice_id)} → ${escape(agent.action.action_id)}</h3><p>${escape(sourceName(p.target_country??p.recipient_type))} · ${escape(label(p.resource??'非移転'))} · 選択量 ${format(p.amount)}</p><div class="decision-numbers">${[['決済要求',requested],['実現',realized],['未達',unmet]].map(([key,value])=>`<div><span>${key}</span><strong>${format(value)}</strong></div>`).join('')}</div>${!agent.flows.length?'<p class="subtle">移転記録なし。条件不成立・非移転行動を、要求0の移転として補完しません。</p>':''}<details open><summary>conditions / 成立判定</summary><div>${Object.keys(response.conditions).length?`<ul class="condition-list">${Object.entries(response.conditions).map(([key,value])=>`<li class="${agent.checks[key]?'':'unsatisfied-text'}">${agent.checks[key]?'✓':'×'} ${escape(key)} = ${escape(JSON.stringify(value))}</li>`).join('')}</ul>`:'<p>実行条件なし。</p>'}<p>自己主権負担 ${format(response.sovereignty_burden)}。条件は参加と選択量で評価され、決済後の実現量を保証しません。</p></div></details><details><summary>materialized action / Python復元</summary><div><pre>${json(agent.action)}</pre></div></details><details><summary>source evidence / 証拠の原点</summary><div><p>run_id</p><code>${escape(model.runId)}</code><p>call_id</p><code>${escape(agent.evidence.callId)}</code><p>timeline field path</p><code>${escape(agent.evidence.pointer)}</code><p>source commit</p><code>${escape(model.sourceCommit)}</code><p>原本SHA-256</p><pre>${json(model.sourceHashes)}</pre><p>検証済み原回答（公開理由のみ）</p><pre>${json(response)}</pre><p>atomic record</p><pre>${json(agent.flows.map(({evidence,target,...record})=>record))}</pre><p class="source-links"><a href="${escape(model.source)}#${escape(agent.evidence.pointer)}">timeline JSON ↗</a> · <a href="${escape(config.researchBundle)}">decision / transport audit ↗</a></p></div></details>`;
  $('#evidence-dialog').showModal();
}

function bindAgents(root) { root.querySelectorAll('[data-agent]').forEach(button=>button.addEventListener('click',()=>openAgent(button.dataset.agent))); }
function bindTurnChoices(root) {
  root.querySelectorAll('[data-turn]').forEach(button=>{
    button.addEventListener('click',()=>selectTurn(Number(button.dataset.turn)));
    if (button.tagName.toLowerCase() === 'g') button.addEventListener('keydown',event=>{if (['Enter',' '].includes(event.key)){event.preventDefault();selectTurn(Number(button.dataset.turn));}});
  });
}
function selectTurn(index) {
  const active = document.activeElement;
  const focusScope = active?.closest('#turn-buttons') ? '#turn-buttons' : active?.closest('#recovery') ? '#recovery' : active?.closest('#trajectory') ? '#trajectory' : null;
  state.index=Math.max(0,Math.min(model.turns.length-1,index));
  render();
  if (focusScope) $(`${focusScope} [data-turn="${state.index}"]`)?.focus({preventScroll:true});
  $('#turn-announcement').textContent=`TURN ${current().number}、${current().event}`;
}
function selectLens(lens) {
  state.lens=lens;
  document.querySelectorAll('[data-lens]').forEach(button=>{const selected=button.dataset.lens===lens;button.setAttribute('aria-selected',String(selected));button.tabIndex=selected?0:-1;$(`#${button.dataset.lens}-panel`).hidden=!selected;});
}
function render() {renderTrajectory();renderNetwork();renderFlows();renderRecovery();renderResearchDepth();selectLens(state.lens);}

async function load() {
  const response=await fetch('observatory/config.json');
  if (!response.ok) throw new Error('Configuration unavailable');
  config=await response.json();
  for (const key of ['timeline','report','researchBundle']) {
    const url=new URL(config[key],location.href);
    if (url.origin!==location.origin || !['http:','https:'].includes(url.protocol)) throw new Error('Invalid evidence location');
  }
  const raw=await fetch(config.timeline);
  if (!raw.ok) throw new Error('Timeline unavailable');
  const bytes=await raw.arrayBuffer();
  const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('');
  if (hash!==config.sha256) throw new Error('Evidence hash mismatch');
  const data=JSON.parse(new TextDecoder().decode(bytes));
  model=projectWorldline(data,config.timeline);
  if (model.runId!==config.runId) throw new Error('Configured run mismatch');
  $('#resource-select').innerHTML=model.resources.map(resource=>`<option value="${escape(resource)}">${escape(label(resource))}</option>`).join('');
  state.resource=model.resources.includes('food')?'food':model.resources[0];
  $('#resource-select').value=state.resource;
  const moments=discoverMoments(model);
  $('#moments').innerHTML=moments.map((moment,index)=>`<button class="moment" data-moment="${index}"><small>TURN ${String(moment.turn).padStart(2,'0')} ↗</small><strong>${escape(moment.title)}</strong><span>${moment.kind==='convergence'?`${moment.agents}国家 / ${format(moment.requested)} → ${format(moment.realized)}`:escape(moment.agent)}</span></button>`).join('');
  $('#moments').querySelectorAll('button').forEach(button=>button.addEventListener('click',()=>{
    const moment=moments[Number(button.dataset.moment)];
    state.lens=moment.kind==='boundary'?'conditions':'flows';
    if(moment.resource){state.resource=moment.resource;$('#resource-select').value=state.resource;}
    selectTurn(moment.turn-1);$('.lens').scrollIntoView({behavior:'instant',block:'start'});
    if(moment.kind==='boundary') $(`#network [data-agent="${moment.agent}"]`).focus({preventScroll:true});
  }));
  $('.intro-note span').textContent=`${model.turns.length}つの観測点。${model.turns.reduce((sum,t)=>sum+t.agents.length,0)}の国家判断。光の向こうに、根拠がある。`;
  $('#run-meta').innerHTML=`${escape(model.runId)}<br>${model.turns.length} TURN · ${model.calls} recorded calls · retry ${model.retry}<br>この閲覧によるGemini API calls: 0<br><a href="${escape(config.report)}">Research artifact ↗</a> · <a href="${escape(model.source)}">Source timeline ↗</a>`;
  const locationState=new URLSearchParams(location.hash.slice(1));
  const requestedTurn=Number(locationState.get('turn'));
  if(Number.isInteger(requestedTurn)&&requestedTurn>=1&&requestedTurn<=model.turns.length)state.index=requestedTurn-1;
  if(['conditions','flows','recovery'].includes(locationState.get('lens')))state.lens=locationState.get('lens');
  render();$('#load-status').hidden=true;$('#experience').hidden=false;document.body.dataset.ready='true';
}
$('#previous').addEventListener('click',()=>selectTurn(state.index-1));
$('#next').addEventListener('click',()=>selectTurn(state.index+1));
$('#extra-metric').addEventListener('change',event=>{state.extra=event.target.value;renderTrajectory();});
$('#resource-select').addEventListener('change',event=>{state.resource=event.target.value;renderFlows();});
const tabs=[...document.querySelectorAll('[data-lens]')];
tabs.forEach((button,index)=>{
  button.addEventListener('click',()=>selectLens(button.dataset.lens));
  button.addEventListener('keydown',event=>{
    const offsets={ArrowRight:1,ArrowLeft:-1,Home:-index,End:tabs.length-1-index};
    if (!(event.key in offsets))return;event.preventDefault();const target=tabs[(index+offsets[event.key]+tabs.length)%tabs.length];selectLens(target.dataset.lens);target.focus();
  });
});
$('#about-open').addEventListener('click',()=>$('#about-dialog').showModal());
document.querySelectorAll('[data-close]').forEach(button=>button.addEventListener('click',()=>button.closest('dialog').close()));
load().catch(()=>{$('#load-status').textContent='検証済みデータを読み込めませんでした。HTTPで開いていることと、出典ファイルを確認してください。表示値は補完せず停止しています。';$('#load-status').setAttribute('role','alert');document.body.dataset.ready='error';});
