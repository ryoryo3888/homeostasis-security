'use strict';
(() => {
  const mount=document.getElementById('v3-evidence');
  const node=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
  const jsonDetails=(title,value)=>{const d=node('details');d.append(node('summary',title),node('pre',JSON.stringify(value,null,2)));return d;};
  const root=node('details');root.id='v3-validation';root.className='v3-validation';
  root.append(node('summary','保存済み検証データ ／ 模擬判断'));
  const body=node('div');root.append(body);mount.append(root);
  try {
    const data=JSON.parse(document.getElementById('v3-validation-data').textContent);
    if(data.schema_version!==1||data.artifact_class!=='validation_run'||data.research_eligible!==false||data.api_calls!==0||data.decision_origin!=='synthetic_fixture')throw Error('classification');
    if(!Array.isArray(data.cases)||!data.cases.length)throw Error('cases');
    for(const c of data.cases)if(!Array.isArray(c.turns)||!c.turns.length||c.turns.some((t,i)=>t.turn!==i+1||t.states.length!==8))throw Error('turns');
    body.append(node('p','検証データ／模擬判断。Gemini実通信 0回。正式研究結果ではありません。上部の地球・国家表示は合成初期状態のままです。'));
    const controls=node('div');controls.className='validation-controls';body.append(controls);
    function selector(title,id){const label=node('label',title+' ');const s=node('select');s.id=id;label.append(s);controls.append(label);return s;}
    const caseSelect=selector('ケース','validation-case'),turnSelect=selector('保存TURN','validation-turn'),stateSelect=selector('国家','validation-state');
    for(const c of data.cases){const o=node('option',c.label);o.value=c.id;caseSelect.append(o);}
    const previous=node('button','‹ 前の保存TURN'),next=node('button','次の保存TURN ›');previous.type=next.type='button';controls.append(previous,next);
    const status=node('p');status.setAttribute('role','status');body.append(status);
    const output=node('div');output.className='validation-output';body.append(output);
    let selectedCase=data.cases[0],turn=selectedCase.turns[0];
    const name=id=>{const s=turn.states.find(s=>s.id===id);return s?s.label+'国':id;};
    const res=id=>({food:'食料',energy:'エネルギー'})[id]||id;
    function table(headers,rows){const wrap=node('div');wrap.className='validation-table';const t=node('table'),head=node('thead'),tr=node('tr');for(const h of headers){const th=node('th',h);th.scope='col';tr.append(th);}head.append(tr);t.append(head);const b=node('tbody');for(const row of rows){const r=node('tr');for(const value of row)r.append(node('td',String(value)));b.append(r);}t.append(b);wrap.append(t);return wrap;}
    function render(){
      turn=selectedCase.turns[Number(turnSelect.value)-1];const sid=stateSelect.value;
      previous.disabled=turn.turn===1;next.disabled=turn.turn===selectedCase.turns.length;
      status.textContent=`検証データ · ${selectedCase.label} · 保存TURN ${turn.turn} / ${selectedCase.turns.length}`;
      output.replaceChildren();
      const states=turn.states.filter(s=>!sid||s.id===sid);
      output.append(node('h3','TURN末の在庫と必須需要'));
      output.append(table(['国家','資源・単位','期末在庫','必須需要','実消費','不足'],states.flatMap(s=>s.resources.map(r=>[name(s.id),res(r.id)+' / '+r.unit,r.stock,r.required,r.consumed,r.shortage]))));
      output.append(node('p','在庫はTURN末の量。不足は必須需要−実消費。未成立量とは別です。'));
      output.append(node('h3','模擬判断 → 共同決済'));
      const tx=turn.transactions.filter(t=>!sid||t.actor===sid);
      if(!tx.length)output.append(node('p','この選択範囲には提出Choiceがありません。明示的拒否とは区別します。'));
      for(const a of tx){
        const box=node('details');box.className='validation-transaction';
        const outcome=a.settled===0?'不成立':a.settled===a.requested?'全量成立':'部分成立';
        box.append(node('summary',`${name(a.actor)} → ${name(a.target)} · ${res(a.resource)} · ${outcome}`));
        box.append(node('p','Choice ID: '+a.choice_id),node('p','公開理由（模擬）: '+a.public_reason));
        box.append(table(['要求','個別可能','共同成立','未成立','発送','このChoiceの累積到着'],[[a.requested,a.feasible,a.settled,a.unsettled,a.dispatched,a.arrived]]));
        box.append(node('p','抽出証拠のJSON pointer: '+a.evidence_pointer));
        box.append(node('p','理由コード: '+(a.reason_codes.join(' / ')||'なし')));
        box.append(jsonDetails('条件・同意', {conditions:a.conditions,consents:a.consents}),jsonDetails('Python復元行動・状態反映', {materialized_action:a.materialized_action,state_change:a.state_change,trace_id:a.trace_id}));output.append(box);
      }
      output.append(node('h3','発送・輸送中・到着'));
      const shipments=turn.shipments.filter(s=>!sid||s.source===sid||s.target===sid);
      output.append(table(['供給元 → 受取先','資源','発送量','到着済量','発送TURN','到着予定','実到着TURN'],shipments.map(s=>[name(s.source)+' → '+name(s.target),res(s.resource),s.dispatched_amount,s.arrived_amount,s.dispatch_turn,s.arrival_due_turn,s.arrival_turn===null?'未着荷':s.arrival_turn])));
      if(!shipments.length)output.append(node('p','保存記録に該当するshipmentなし。'));
      output.append(node('p','成立・発送と到着は別です。過去TURNの発送も含み、未着荷を受取国の在庫に加算しません。'));
      const production=turn.production.filter(p=>!sid||p.owner===sid);
      output.append(node('h3','生産・投入と世界収支'));
      output.append(table(['国家','資源','生産量','在庫化TURN','投入資源'],production.map(p=>[name(p.owner),res(p.resource),p.quantity,p.available_turn,p.inputs.map(i=>res(i.resource)+' '+i.amount).join(' / ')||'定義された投入なし'])));
      output.append(jsonDetails('世界全体の資源別収支',turn.conservation),jsonDetails('外乱・経路予約量',{events:turn.events,reservations:turn.reservations}));
      const proof=node('details');proof.append(node('summary','原本との対応・監査証拠'));
      proof.append(node('p','Checkpoint digest: '+turn.checkpoint_digest));
      const link=node('a','抽出証拠JSON（原本pointer・値digest・実行ソースcommit）');link.href='ui/v3/validation/evidence.json';proof.append(link);
      proof.append(node('p',`JSON pointer: /cases/${data.cases.indexOf(selectedCase)}/turns/${turn.turn-1}/evidence`));
      proof.append(node('p','原本は変更せず、17観測を元checkpointから再計算照合済み。公開ファイルは必要部分の抽出であり、完全checkpointや正式研究結果ではありません。'));
      output.append(proof);
    }
    function changeCase(){selectedCase=data.cases.find(c=>c.id===caseSelect.value);turnSelect.replaceChildren();for(const t of selectedCase.turns){const o=node('option',String(t.turn));o.value=t.turn;turnSelect.append(o);}stateSelect.replaceChildren();const all=node('option','8国家');all.value='';stateSelect.append(all);for(const s of selectedCase.turns[0].states){const o=node('option',s.label+'国');o.value=s.id;stateSelect.append(o);}render();}
    caseSelect.addEventListener('change',changeCase);turnSelect.addEventListener('change',render);stateSelect.addEventListener('change',render);
    previous.addEventListener('click',()=>{turnSelect.value=turn.turn-1;render();});next.addEventListener('click',()=>{turnSelect.value=turn.turn+1;render();});
    changeCase();
    function openHash(){if(location.hash==='#v3-validation'){root.open=true;root.scrollIntoView({block:'start'});}}
    addEventListener('hashchange',openHash);openHash();
    window.V3Validation=Object.freeze({ready:true,artifactClass:'validation_run',researchEligible:false});
  } catch(error){body.replaceChildren(node('p','検証データを確認できません。結果は表示していません。'));window.V3Validation=Object.freeze({ready:false});}
})();
