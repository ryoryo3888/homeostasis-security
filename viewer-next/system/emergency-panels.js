"use strict";
// VIS-02 / D-1〜3 の表示用。実アラート・承認・通知は生成しない。
globalThis.HS_EMERGENCY_PANELS = () => {
  const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
  const panel=(title,cls)=>{const p=node('section',undefined,'panel layout-panel '+cls);p.append(node('h2',title));return p;};
  const rows=items=>{const dl=node('dl');for(const [k,v] of items)dl.append(node('dt',k),node('dd',v));return dl;};
  const request=()=>{
    const p=panel('判断要求｜発火源未接続','emergency-request reference-panel');
    p.append(node('p','実際の緊急アラートではありません。','status-unconnected'),rows([
      ['対象・事象ID','未取得'],['確定判定・予測根拠','未接続'],['影響する地域・主体','未確定'],
      ['発生時刻・判断期限','未取得・未確定'],['情報品質・校正','未検証']]),node('p','重要度や危険度を画面側で計算しません。実アラート音は鳴動しません。この候補には音声試聴・通知送信の機能もありません。','quiet'));
    return p;
  };
  const authority=()=>{
    const p=panel('人間の最終判断｜認可未成立','authority-panel');
    p.append(node('p','未認証・判断未登録','status-unconnected'),rows([
      ['権限を有する判断者','未検証'],['選択中の案・参照世界版','未指定・未確定'],
      ['影響・代替案・関係主体','未照合'],['入力の確認・再認証','未成立']]),
      node('p','AIによる承認・実行は行いません。承認権限を検証できないため、承認操作は表示しません。','quiet'));
    const a=node('a','入力・実行が無効であることを確認');a.href='#readonly-boundary';p.append(a);
    return p;
  };
  const history=()=>{
    const p=panel('判断・通知・実行の関連履歴','emergency-history');
    p.append(rows([['監査用関連ID','未取得'],['通知送信／到達／確認','未接続・未確認'],['判断登録／実行要求','未登録・未発行'],['実行結果／結果観測','未確認・未取得']]),
      node('p','表示操作・音の停止・判断・実行の状態は別です。実際の履歴がないため、時刻付きの架空ログは表示しません。','quiet'));
    p.append(node('p','この閲覧候補には音声試聴・停止・通知操作はありません。','quiet'));
    return p;
  };
  return {request,authority,history};
};
