"use strict";
// 端末時計だけ。観測時刻・世界時間・比較時点の代用にはしない。
globalThis.HS_TERMINAL_TIME = epochMilliseconds => {
  if(typeof epochMilliseconds!=='number'||!Number.isSafeInteger(epochMilliseconds))return {known:false,reason:'端末時計の値が不正です'};
  const date=new Date(epochMilliseconds);
  if(!Number.isFinite(date.getTime()))return {known:false,reason:'端末時計を表示できません'};
  const format=zone=>new Intl.DateTimeFormat('ja-JP',{timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).format(date);
  return {known:true,jst:format('Asia/Tokyo'),utc:format('UTC'),clockSynchronizationVerified:false,worldTimeVerified:false};
};
globalThis.HS_TIME_DISPLAY = () => {
  const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
  const refresh=()=>{
    let clock;try{clock=globalThis.HS_TERMINAL_TIME(Date.now());}catch(_){clock={known:false,reason:'端末時計の読出し・表示に失敗しました'};}
    for(const target of document.querySelectorAll('[data-terminal-clock]'))target.textContent=clock.known?clock[target.dataset.terminalClock]:clock.reason;
  };
  const appendClocks=list=>{
    for(const [label,key] of [['端末時計（JST）','jst'],['端末時計（UTC）','utc']]){const value=node('dd','未読出し');value.dataset.terminalClock=key;list.prepend(node('dt',label),value);}
  };
  const timeline=layout=>{
    const panel=node('section',undefined,'panel layout-panel timeline-panel');panel.append(node('h2','時系列・再生｜参照記録未接続'));
    const toolbar=node('div',undefined,'timeline-toolbar');
    for(const label of ['再生（保存系列未接続）','時間指定（計算済み時点なし）','ライブ追従（未接続）']){const b=node('button',label);b.type='button';b.disabled=true;toolbar.append(b);}panel.append(toolbar);
    const facts=node('dl');for(const [k,v] of [['開始・終了時点','未確定'],['表示中の時点・再生位置','未選択'],['世界版・実行ID・分岐ID','未対応づけ']])facts.append(node('dt',k),node('dd',v));panel.append(facts);
    const lanes=node('div',undefined,'time-lanes');lanes.setAttribute('role','group');lanes.setAttribute('aria-label','観測と予測を分離した時系列の表示構造');
    const names=['地球状態の現実観測｜未取得','推定状態｜未算出'];if(['comparison','comparison-detail','crisis','emergency'].includes(layout))names.push('実行した未来｜未算出','非実行の未来｜未算出','別選択の未来｜未算出');
    for(const name of names){const row=node('div',undefined,'time-lane');row.append(node('span',name),node('div','系列未接続','unconnected-series'));lanes.append(row);}panel.append(lanes,node('p','端末の現在時刻と、世界時間・観測時刻・予測時点は別です。保存済みの入力・応答・版の接続がないため、点・目盛の日付・曲線を作りません。再生による世界への書戻しやLLM再呼出しは行いません。','quiet'));return panel;
  };
  return {refresh,appendClocks,timeline};
};
