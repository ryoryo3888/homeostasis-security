/* HOMEOSTASIS SECURITY — research narrative layer
   Preview-only enhancement. It does not change simulation data, metrics, graphs, Earth visuals, or source dashboards. */
(() => {
  'use strict';

  const FILES_V1 = {
    A:'simulation_result_cautious_cautious_law_hotline_run1.json',
    B:'result_hardliner_law_hotline_run1.json',
    C:'result_cautious_no_law_hotline_run1.json',
    D:'simulation_result_cautious_cautious_law_no_hotline_run1.json',
    E:'result_hardliner_no_law_no_hotline_run1.json',
    F:'result_hardliner_no_law_hotline_run1.json',
    G:'result_hardliner_law_no_hotline_run1.json',
    H:'result_cautious_no_law_no_hotline_run1.json',
    I:'result_hardliner_cautious_law_hotline_run1.json',
    J:'result_hardliner_cautious_law_no_hotline_run1.json',
    K:'result_hardliner_cautious_no_law_hotline_run1.json',
    L:'result_hardliner_cautious_no_law_no_hotline_run1.json',
    M:'result_cautious_hardliner_law_hotline_run1.json',
    N:'result_cautious_hardliner_law_no_hotline_run1.json',
    O:'result_cautious_hardliner_no_law_hotline_run1.json',
    P:'result_cautious_hardliner_no_law_no_hotline_run1.json'
  };

  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const short = (s, n=86) => { const t=String(s ?? '').replace(/\s+/g,' ').trim(); return t.length>n ? t.slice(0,n-1)+'…' : t; };
  const n = v => Number.isFinite(Number(v)) ? Number(v) : null;
  const fmt = v => n(v)===null ? '—' : String(Math.round(Number(v)*10)/10);
  const el = (tag, cls, html='') => { const x=document.createElement(tag); if(cls)x.className=cls; x.innerHTML=html; return x; };
  const $ = (s, root=document) => root.querySelector(s);
  const $$ = (s, root=document) => [...root.querySelectorAll(s)];

  function scrollToTurn(turn){
    const button = document.querySelector(`[data-turn="${turn}"]`);
    if(button){ button.click(); button.scrollIntoView({behavior:'smooth',block:'center'}); }
  }

  function section(title, kicker=''){
    return `<div class="rn-section-head">${kicker?`<span>${esc(kicker)}</span>`:''}<h2>${esc(title)}</h2></div>`;
  }

  function metric(label, before, after, note=''){
    const delta = n(before)!==null && n(after)!==null ? Number(after)-Number(before) : null;
    const arrow = delta===null ? '→' : delta>0 ? '↑' : delta<0 ? '↓' : '→';
    return `<div class="rn-metric"><span>${esc(label)}</span><strong>${esc(fmt(before))} → ${esc(fmt(after))} ${arrow}</strong>${note?`<small>${esc(note)}</small>`:''}</div>`;
  }

  function insertLayer(){
    if($('#homeostasisResearchLayer')) return $('#homeostasisResearchLayer');
    const root=el('section','research-narrative panel');
    root.id='homeostasisResearchLayer';
    const anchor = $('.controls') || $('.simulation-control');
    if(anchor) anchor.parentNode.insertBefore(root, anchor);
    else ($('main')||document.body).prepend(root);
    return root;
  }

  function turningPointsV1(results){
    const scored=[];
    for(let i=1;i<results.length;i++){
      const a=results[i-1].metrics||{}, b=results[i].metrics||{};
      const keys=['homeostasis','tension','resilience','trust','misperception_risk'];
      const score=keys.reduce((sum,k)=>sum+Math.abs((n(b[k])??0)-(n(a[k])??0)),0);
      scored.push({turn:i+1,score});
    }
    return new Set(scored.sort((a,b)=>b.score-a.score).slice(0,2).map(x=>x.turn));
  }

  function v1TurnCards(data){
    const results=data.results||[];
    const points=turningPointsV1(results);
    return results.map((r,i)=>{
      const t=i+1, ev=r.external_event||{}, m=r.metrics||{};
      return `<button type="button" class="rn-turn ${points.has(t)?'is-turning':''}" data-rn-turn="${t}">
        <span class="rn-turn-no">TURN ${t}${points.has(t)?' · 転換点':''}</span>
        <strong>${esc(ev.title||'世界状態を更新')}</strong>
        <small>A国：${esc(short((r.country_a||{}).action,62))}</small>
        <small>B国：${esc(short((r.country_b||{}).action,62))}</small>
        <span class="rn-turn-metrics">緊張 ${esc(fmt(m.tension))} ／ 恒常性 ${esc(fmt(m.homeostasis))} ／ 回復力 ${esc(fmt(m.resilience))}</span>
      </button>`;
    }).join('');
  }

  function buildV1Findings(summary){
    const conditions=(summary&&summary.conditions)||[];
    if(!conditions.length) return [];
    const groups=new Map();
    conditions.forEach(c=>{
      const pair=String(c.label||'').split('/')[0].trim();
      if(!groups.has(pair)) groups.set(pair,[]);
      groups.get(pair).push(c);
    });
    let widest=null;
    for(const [pair,arr] of groups){
      if(arr.length<2) continue;
      const es=arr.map(x=>n(x.escalation_pressure_mean)).filter(x=>x!==null);
      const rs=arr.map(x=>n(x.recovery_capacity_mean)).filter(x=>x!==null);
      if(!es.length||!rs.length) continue;
      const score=(Math.max(...es)-Math.min(...es))+(Math.max(...rs)-Math.min(...rs));
      if(!widest||score>widest.score) widest={pair,arr,score,emin:Math.min(...es),emax:Math.max(...es),rmin:Math.min(...rs),rmax:Math.max(...rs)};
    }
    const cautious=conditions.filter(c=>String(c.label||'').startsWith('慎重外交型×慎重外交型'));
    const over=Math.max(0,...cautious.map(c=>n(c.reaction_axis?.overall?.overreaction_rate)??0));
    const under=Math.max(0,...cautious.map(c=>n(c.reaction_axis?.overall?.underreaction_rate)??0));
    const findings=[];
    if(widest) findings.push({title:'同じ国家類型でも、制度条件で結果が変わった',body:`${widest.pair}では、条件の違いだけでエスカレーション圧は ${fmt(widest.emin)}〜${fmt(widest.emax)}、回復力は ${fmt(widest.rmin)}〜${fmt(widest.rmax)} の幅が観測されました。国家類型だけでは結果を説明できません。`});
    findings.push({title:'慎重な国家でも、いつも適応的とは限らなかった',body:`慎重外交型×慎重外交型の条件群でも、最大で過剰反応 ${fmt(over)}%、過少反応 ${fmt(under)}% が観測されました。「緊張が低いこと」と「脅威に適切に反応すること」は同じではありません。`});
    findings.push({title:'単一の数字では条件の良し悪しを決められない',body:'HOMEOSTASIS SECURITYでは、緊張だけでなく、脅威に対する反応の強さ、回復力、信頼、過剰反応・過少反応を合わせて観測します。'});
    return findings;
  }

  async function renderV1(root){
    const code=($('#worldCondition')||{}).value||'A';
    root.innerHTML=`${section('二国間の危機は、どうすれば平衡へ戻れるのか？','研究質問')}
      <div class="rn-intro-grid">
        <div class="rn-brief"><h3>この世界を10秒で理解</h3><p><b>A国・B国</b>は、それぞれ独立して安全と利益を守ろうと判断します。国際法と緊急連絡窓口の有無、国家の判断傾向を変えながら、危機への反応と回復を観測します。</p><p class="rn-plain">独立評価役は各国の判断には参加せず、脅威と反応の釣り合いを後から評価します。</p></div>
        <div class="rn-route"><b>読み方</b><span>① 8ターンで何が起きた？</span><span>② 16条件・36回へ広げると何が見えた？</span><span>③ そこから、なぜ地球規模の実験へ進んだ？</span></div>
      </div>
      <div id="rnV1Dynamic" class="rn-loading">代表実験を読み込んでいます。</div>`;
    try{
      const [data,summary]=await Promise.all([
        fetch(FILES_V1[code]).then(r=>{if(!r.ok)throw new Error('代表実験');return r.json();}),
        fetch('summary.json').then(r=>r.ok?r.json():null).catch(()=>null)
      ]);
      const results=data.results||[], first=results[0]||{}, last=results[results.length-1]||{};
      const findings=buildV1Findings(summary);
      const dyn=$('#rnV1Dynamic',root);
      dyn.className='';
      dyn.innerHTML=`
        ${section('この8ターンで何が起きた？','30秒で理解')}
        <p class="rn-lead">条件 <b>${esc(code)}</b> の代表実験では、目的の分からない軍事行動や不確かな情報、通信障害などに対し、A国とB国が毎ターン独立して判断しました。下のカードは実際の保存データを、人が追いやすい順に並べたものです。</p>
        <div class="rn-turn-grid">${v1TurnCards(data)}</div>
        <p class="rn-caption">「転換点」は、前のターンから緊張・恒常性・回復力・信頼・誤認リスクの変化量が特に大きかったターンを自動表示しています。</p>
        <div class="rn-metrics-row">
          ${metric('恒常性',(first.metrics||{}).homeostasis,(last.metrics||{}).homeostasis,'世界が平衡へ戻れているか')}
          ${metric('緊張',(first.metrics||{}).tension,(last.metrics||{}).tension,'低ければ常に良い、という指標ではありません')}
          ${metric('回復力',(first.metrics||{}).resilience,(last.metrics||{}).resilience,'危機後に安定へ戻る力')}
        </div>
        ${section('1つの世界線から、16条件・36回へ','研究の成長')}
        <p class="rn-lead">最初の実験だけでは「この条件だから回復した」とは言えません。そこで国家の判断傾向、国際法、緊急連絡窓口を組み替え、A〜Pの16条件・合計36回へ拡張しました。</p>
        <div class="rn-findings">${findings.map(f=>`<article><h3>${esc(f.title)}</h3><p>${esc(f.body)}</p></article>`).join('')}</div>
        <div class="rn-bridge">
          <span>V1</span><b>二国間は平衡を回復できるか？</b><i>↓</i>
          <span>16条件・36回</span><b>何が回復を左右するのか？</b><i>↓</i>
          <span>次の問い</span><b>二国間で生じた被害は、食料・経済・第三国を通じて世界へ広がったとき、どうなるのか？</b><i>↓</i>
          <span>V2</span><b>国家が自分で判断する余地を保ったまま、地球規模の恒常性は成立するのか？</b>
        </div>
        <div class="rn-next"><h3>この観測から、次の問いが生まれました</h3><p>局所的な危機が二国間で収束しても、その被害が食料市場や第三国へ波及したら、局所的な回復だけで十分なのでしょうか。</p><a href="dashboard_v2.html">地球規模へ広げたV2を見る →</a></div>
        <details class="rn-depth"><summary>研究者向け：数値・グラフ・原データまで検証する</summary><p>この下にある既存の比較グラフ、条件表、ターン表示、イベントログは削除していません。短い説明から入り、必要な人だけ原データへ降りられます。</p></details>`;
      $$('[data-rn-turn]',dyn).forEach(b=>b.addEventListener('click',()=>scrollToTurn(b.dataset.rnTurn)));
    }catch(err){
      $('#rnV1Dynamic',root).innerHTML='<p class="rn-warning">代表実験を読み込めませんでした。既存Dashboardはそのまま利用できます。</p>';
    }
  }

  function v2Turning(turn, prev){
    if(!prev) return false;
    const c=(turn.countries||{}).C||{}, pc=(prev.countries||{}).C||{};
    const b=(turn.countries||{}).B||{}, pb=(prev.countries||{}).B||{};
    const p=(turn.coordinator_proposal||{}).proposal, pp=(prev.coordinator_proposal||{}).proposal;
    return c.action!==pc.action || b.action!==pb.action || p!==pp;
  }

  function v2TurnCards(data){
    return (data.turns||[]).map((t,i)=>{
      const prev=i?data.turns[i-1]:null, turning=v2Turning(t,prev), ws=t.world_state||{}, c=(t.countries||{}).C||{}, b=(t.countries||{}).B||{};
      return `<button type="button" class="rn-turn ${turning?'is-turning':''}" data-rn-turn="${t.turn}">
        <span class="rn-turn-no">TURN ${t.turn}${turning?' · 転換点':''}</span>
        <strong>${turning?'行動や提案が前ターンから変化':'危機への対応を継続'}</strong>
        <small>B国：${esc(short(b.action,58))}</small>
        <small>C国：${esc(short(c.action,58))}</small>
        <span class="rn-turn-metrics">地球恒常性 ${esc(fmt(ws.global_homeostasis))} ／ 主権 ${esc(fmt(ws.national_sovereignty))} ／ 紛争負荷 ${esc(fmt(ws.conflict_load))}</span>
      </button>`;
    }).join('');
  }

  async function renderV2(root){
    root.innerHTML=`${section('国家が自分で判断する余地を保ったまま、地球規模の恒常性は成立するのか？','研究質問')}<div id="rnV2Dynamic" class="rn-loading">実験データを読み込んでいます。</div>`;
    try{
      const data=