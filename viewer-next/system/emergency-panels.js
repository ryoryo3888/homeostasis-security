"use strict";
// VIS-02 / D-1〜3 の表示用。実アラート・承認・通知は生成しない。
globalThis.HS_EMERGENCY_PANELS = () => {
  const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
  const panel=(title,cls)=>{const p=node('section',undefined,'panel layout-panel '+cls);p.append(node('h2',title));return p;};
  const rows=items=>{const dl=node('dl');for(const [k,v] of items)dl.append(node('dt',k),node('dd',v));return dl;};
  const request=()=>{
    const p=panel('判断要求｜発火源未接続','emergency-request reference-panel');
    p.append(node('p','実際の緊急アラートではありません。','status-unconnected'),rows([
      ['何が起きたか（対象・事象ID）','未取得'],['なぜ人の判断が必要か','未判定・根拠未接続'],
      ['判断期限','未確定'],['まだ分からないこと','確定判定・予測根拠・影響・情報品質'],
      ['影響する地域・主体','未確定'],['発生時刻','未取得'],['情報品質・校正','未検証']]),node('p','重要度や危険度を画面側で計算しません。実アラート音は鳴動しません。この候補には音声試聴・通知送信の機能もありません。','quiet'));
    return p;
  };
  const authority=()=>{
    const p=panel('人間の最終判断｜認可未成立','authority-panel');
    p.append(node('p','未認証・判断未登録','status-unconnected'),rows([
      ['権限を有する判断者','未検証'],['選択中の案・参照世界版','未指定・未確定'],
      ['影響・代替案・関係主体','未照合'],['入力の確認・再認証','未成立']]),
      node('p','AIによる承認・実行は行いません。承認権限を検証できないため、承認操作は表示しません。','quiet'));
    const a=node('a','入力・実行が無効であることを確認');a.href='#readonly-boundary';p.append(a,rows([['現在の根拠提示版（人間に見せる内容）','未取得'],['参照世界版・権限との照合','未照合']]));
    return p;
  };
  const history=()=>{
    const p=panel('判断・通知・実行の関連履歴','emergency-history');
    p.append(rows([['監査用関連ID','未取得'],['通知送信／到達／確認','未接続・未確認'],['判断登録／実行要求','未登録・未発行'],['実行結果／結果観測','未確認・未取得']]),
      node('p','表示操作・音の停止・判断・実行の状態は別です。実際の履歴がないため、時刻付きの架空ログは表示しません。','quiet'));
    p.append(node('p','この閲覧候補には音声試聴・停止・通知操作はありません。','quiet'));
    return p;
  };
  // Public static presentation only. No observation, submission or execution interfaces.
  const entry=(description,label,openEvidence)=>{
    const block=node('div',undefined,'judgment-entry');
    const button=node('button',label);button.type='button';
    button.addEventListener('click',openEvidence);
    block.append(node('p',description),button);return block;
  };
  const evidence=()=>{
    const p=panel('人間の判断に使う根拠','judgment-evidence');
    p.id='judgment-evidence';p.tabIndex=-1;
    p.firstElementChild.append(node('span','表示見本・試験データ／本番未接続','judgment-preview-badge'));
    p.append(node('p','現在は照合欄の見本です。実際の事象・閾値・判断結果は表示せず、承認・通知・実行も行いません。'));
    const detail=node('details');detail.append(node('summary','基準・当時の説明・証拠区分を確認'));
    const grid=node('div',undefined,'judgment-grid');
    const add=(title,items,note)=>{
      const card=node('section');card.append(node('h3',title),rows(items),node('p',note));grid.append(card);
    };
    add('何を判断する基準か',[
      ['基準の意味・判断対象','未取得'],['基準の定義ID・版','未取得'],['適用条件・対象範囲','未照合'],
      ['この事象への適用可否','未判定'],['適用に使った入力・観測版','未取得']
    ],'基準が何を指すかと、参照した定義のID・版は別に確認します。');
    add('基準値と計算結果',[
      ['閾値・比較方法','未設定'],['閾値の単位','未確認'],['計算値・計算の参照版','未算出'],
      ['計算値の単位','未確認'],['照合結果','未判定']
    ],'未取得・未算出は、0・安全・不適用のどれも意味しません。');
    add('判断当時に提示した材料',[
      ['説明本文','記録なし（表示見本）'],['説明のID・版','未取得'],['提示日時・参照世界版','未取得'],
      ['判断要求・判断記録との対応','未照合'],['当時示した基準値・計算値・単位','記録なし（表示見本）'],
      ['当時分からないと示した項目','記録なし（表示見本）']
    ],'後から生成した文を「当時の説明」として代用しません。');
    add('証拠の区分と参照',[
      ['判断依頼に使った根拠の参照版','未取得'],['人間に提示した根拠の参照版','未取得'],
      ['観測事実・原データ（RAW）','未取得'],['推定・予測','未算出'],['世界内部状態・演算の記録','未接続'],
      ['物理的変化・適用結果','未確認'],['根拠の出典・記録ID・版','未取得'],['根拠の閲覧権限','未検証']
    ],'試験用の枠だけを示しています。実際の根拠や非公開の参照先は表示しません。');
    add('後から追加・改訂された説明',[
      ['後着・訂正・追記の差分と理由','記録なし（表示見本）'],['改訂版・作成日時','未取得'],
      ['元の説明版への参照','未照合']
    ],'改訂された説明は当時の説明とは別に扱い、上書きしません。');
    detail.append(grid);p.append(detail);return p;
  };
  return {request,authority,history,entry,evidence};
};
