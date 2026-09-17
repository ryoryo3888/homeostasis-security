import {projectWorldline, discoverMoments, summarizeFlows, resolvePointer} from '../../observatory/view-model.js';
let count=0;
const assert=(value,message)=>{if(!value)throw Error(message); count++;};
const freeze=o=>{if(o&&typeof o==='object'){Object.values(o).forEach(freeze);Object.freeze(o);}return o;};
const reject=(data,change)=>{const copy=structuredClone(data);change(copy);let failed=false;try{projectWorldline(copy,'fixture');}catch{failed=true;}assert(failed,'Invalid evidence must fail closed');};
try {
 const config=await(await fetch('../../observatory/config.json')).json();
 const data=await(await fetch('../../'+config.timeline)).json();
 const before=JSON.stringify(data); freeze(data);
 const model=projectWorldline(data,config.timeline);
 assert(JSON.stringify(data)===before,'Pure projection cannot mutate evidence');
 assert(model.turns.length===8&&model.ids.length===8,'Complete saved worldline');
 assert(model.calls===80&&model.retry===0,'Historical call metadata');
 for(const turn of model.turns){
   for(const agent of turn.agents){assert(resolvePointer(data,agent.evidence.pointer).agent_id===agent.id,'Decision pointer');assert(agent.evidence.runId===model.runId&&agent.evidence.turn===turn.number&&agent.evidence.callId,'Evidence identity');}
   for(const flow of turn.flows)assert(resolvePointer(data,flow.evidence.pointer).realized===flow.realized,'Flow provenance');
 }
 const moments=discoverMoments(model);
 assert(moments[0].turn===4&&moments[0].agents===7&&moments[0].requested===350&&Math.abs(moments[0].realized-50)<1e-8&&moments[0].unmet===300,'Convergence discovered from data');
 const food=summarizeFlows(model.turns[3],'food');assert(food.requested===350&&Math.abs(food.realized-50)<1e-8&&food.unmet===300,'T4 atomic totals');
 const small=model.turns[5].agents.find(a=>a.id==='SMALL');assert(!small.participates&&small.flows.length===0&&!small.checks.maximum_sovereignty_burden,'T6 no fabricated zero transfer');
 assert(moments[2].turn===8&&model.turns[7].flows.some(f=>f.agent_id===moments[2].agent&&f.target===f.agent_id),'T8 self draw');
 reject(data,d=>d.turns[0].decisions[0].materialized_action.parameters.target_country='MIL');
 reject(data,d=>d.turns[0].decisions[0].model_response.choice_id='unknown');
 reject(data,d=>d.turns[0].decisions[0].validation_status='FAIL');
 reject(data,d=>d.turns[0].executed_state.atomic_settlements[0].unmet+=1);
 reject(data,d=>d.turns[0].executed_state.true_world.global_homeostasis=101);
 reject(data,d=>d.validation.research_eligible=false);
 reject(data,d=>d.turns[0].decisions[1].agent_id=d.turns[0].decisions[0].agent_id);
 reject(data,d=>d.turns[0].derived.condition_edges[0].required='unknown');
 const reordered=structuredClone(data);reordered.turns.forEach(t=>t.decisions.reverse());
 assert(JSON.stringify(projectWorldline(reordered,'fixture').turns.map(t=>t.agents.map(a=>a.id)))===JSON.stringify(model.turns.map(t=>t.agents.map(a=>a.id))),'Stable agent layout');
 const frame=document.querySelector('#app');
 for(let i=0;i<100&&frame.contentDocument.body?.dataset.ready!=='true';i++)await new Promise(r=>setTimeout(r,50));
 const doc=frame.contentDocument,win=frame.contentWindow,$=s=>doc.querySelector(s);
 assert(doc.body.dataset.ready==='true','App loaded hash-verified evidence');
 assert($('#previous').disabled,'First turn boundary');
 $('#moments [data-moment="0"]').click();assert($('#turn-number').textContent==='04'&&!$('#flows-panel').hidden,'Convergence navigation');
 assert([...doc.querySelectorAll('#flow-totals strong')].map(n=>n.textContent).join(',')==='350,50,300','Rendered totals');
 assert(doc.querySelectorAll('#flows .flow-row').length===7,'No fabricated flow edges');
 $('#moments [data-moment="1"]').click();assert($('#turn-number').textContent==='06'&&doc.activeElement.dataset.agent==='SMALL','Boundary navigation and focus');
 $('#network [data-agent="SMALL"]').click();assert($('#evidence-dialog').open&&$('#evidence-content').textContent.includes('maximum_sovereignty_burden'),'Decision disclosure');
 assert($('#evidence-content').textContent.includes('移転記録なし')&&$('#evidence-content').textContent.includes('/turns/5/decisions/'),'Deep provenance and absent flow');
 $('#evidence-dialog [data-close]').click();assert(!$('#evidence-dialog').open,'Close modal');
 const button=$('#turn-buttons [data-turn="3"]');button.focus();button.click();assert(doc.activeElement.dataset.turn==='3','Turn focus survives render');
 $('#conditions-tab').focus();$('#conditions-tab').dispatchEvent(new win.KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true}));assert(doc.activeElement.id==='flows-tab'&&$('#flows-tab').getAttribute('aria-selected')==='true','Keyboard tabs');
 $('#recovery-tab').click();assert(doc.querySelectorAll('.recovery-column').length===8,'Recovery observations');
 $('#moments [data-moment="2"]').click();assert($('#turn-number').textContent==='08'&&$('#next').disabled,'Final observation boundary');
 assert(win.matchMedia('(prefers-reduced-motion: reduce)').matches,'Reduced motion preference honored by test browser');
 for(const width of [1440,390,320]){
   frame.style.width=width+'px';await new Promise(r=>setTimeout(r,60));
   for(const lens of ['conditions','flows','recovery']){
     $('#'+lens+'-tab').click();
     assert(doc.documentElement.scrollWidth<=width+2,'No horizontal overflow at '+width+' '+lens);
   }
   $('#conditions-tab').click();$('#network [data-agent="SMALL"]').click();
   assert($('#evidence-dialog').getBoundingClientRect().right<=width,'Dialog within viewport');
   assert(win.getComputedStyle($('#evidence-dialog')).animationName==='none','Reduced motion removes dialog animation');
   $('#evidence-dialog [data-close]').click();
 }
 assert([...doc.querySelectorAll('button')].every(b=>b.textContent.trim()||b.getAttribute('aria-label')),'Named controls');
 document.querySelector('#result').textContent='OBSERVATORY PASS '+count;
} catch(error){document.querySelector('#result').textContent='OBSERVATORY FAIL '+error.message;}

await fetch('/__observatory_test_result', {method:'POST',body:document.querySelector('#result').textContent});
