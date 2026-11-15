"use strict";
// VIS-01/05/06/07 の構造。記録・警報・順位・提案を捏造しない。
globalThis.HS_MONITORING_PANELS = () => {
  const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
  const panel=(title,cls)=>{const p=node('section',undefined,'panel layout-panel '+cls);p.append(node('h2',title));return p;};
  const emptyTable=(columns,description)=>{
    const scroll=node('div',undefined,'table-scroll');scroll.tabIndex=0;scroll.setAttribute('role','region');scroll.setAttribute('aria-label',description);
    const table=node('table');table.append(node('caption',description));const thead=node('thead');const row=node('tr');
    for(const name of columns){const th=node('th',name);th.scope='col';row.append(th);}thead.append(row);table.append(thead,node('tbody'));scroll.append(table);return scroll;
  };
  const overview=()=>{
    const group=node('div',undefined,'monitoring-strip');
    const events=panel('現在の主要事象｜未取得','events-panel');events.append(emptyTable(['時刻','対象・事象','四状態区分・根拠'],'主要事象の実記録は未取得'),node('p','事象の有無・件数・重大度は未判定です。記録がないことを無事件とは扱いません。','quiet'));
    const notes=panel('AI分析ノート｜未生成','analysis-notes-panel');notes.append(emptyTable(['生成時刻','対象・分析内容','入力・演算版'],'実観測と演算に対応する分析ノートは未生成'),node('p','根拠と生成条件が対応した本文は未接続です。時刻付きの仮ノートや政策提案を作りません。','quiet'));
    const regions=panel('地域別評価｜未算出','regional-risk-panel');regions.append(emptyTable(['対象地域','評価・不確実性','根拠・参照版'],'地域別評価の実結果は未算出'),node('p','リスクの順位・増減・警報件数は未算出です。地域の対象範囲と測定定義も未照合です。','quiet'));
    group.append(events,notes,regions);return group;
  };
  const crisis=()=>{
    const group=node('div',undefined,'crisis-analysis-strip');
    const impact=panel('関連する連鎖影響｜未分析','chain-impact-panel');impact.append(emptyTable(['影響対象','因果候補・観測の区別','期間・根拠'],'成立した因果経路・物理的変化は未確認'),node('p','因果関係の候補と、観測済みの物理的変化を分けて扱います。依存関係・時間差が未算出のため矢印や順位は描画しません。','quiet'));
    const proposals=panel('対応案の根拠・適用条件｜未生成','proposal-evidence-panel');proposals.append(emptyTable(['対象候補','成立条件・権限','根拠・不確実性'],'実際の判断候補と成立条件は未取得'),node('p','架空の介入案・推奨順位・改善率は表示しません。候補の閲覧や表示だけで採用・承認・実行は成立しません。','quiet'));
    group.append(impact,proposals);return group;
  };
  return {overview,crisis};
};
