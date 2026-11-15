"use strict";
globalThis.HS_DETAIL_PANELS = (screen, rerender) => {
  const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
  const panel=(title,cls)=>{const p=node('section',undefined,'panel layout-panel '+cls);p.append(node('h2',title));return p;};
  const rows=items=>{const dl=node('dl');for(const [name,value] of items)dl.append(node('dt',name),node('dd',value));return dl;};
  const controls=(values,selected,select,label)=>{
    const group=node('div',undefined,'display-controls');group.setAttribute('role','group');group.setAttribute('aria-label',label);
    for(const value of values){const b=node('button',value);b.type='button';b.setAttribute('aria-pressed',String(value===selected));b.addEventListener('click',()=>{select(value);for(const g of document.querySelectorAll('[role=group]'))if(g.getAttribute('aria-label')===label){for(const target of g.querySelectorAll('button'))if(target.textContent===value){target.focus({preventScroll:true});break;}}});group.append(b);}return group;
  };
  const focusKey=key=>{const target=document.querySelector('[data-focus-key="'+key+'"]');if(target)target.focus({preventScroll:true});};
  const detail=()=>{
    const snapshot=screen.snapshot();const p=panel(snapshot.reportDetail?'レポート項目｜未生成':'個別事象｜未選択','detail-panel');const tab=snapshot.detailTab;
    if(snapshot.reportDetail){p.firstElementChild.dataset.focusKey='report-detail-heading';p.firstElementChild.tabIndex=-1;const c=snapshot.reportDetail;p.append(rows([['元の表示地域',c.region],['元の表示カテゴリ',c.category],['レポート版・対象事象','未生成・未取得'],['元の世界版・対象時刻','未確定'],['根拠の閲覧権限','未検証']]),node('p','未生成状態の表示確認です。実レポート項目や保存済み根拠を開いたことにはなりません。','quiet'));const back=node('button','元のレポート表示条件へ戻る');back.type='button';back.addEventListener('click',()=>{screen.closeReportDetail();rerender('report');focusKey('report-detail-open');});p.append(back);}

    const content={
      '概要':[['事象ID・対象地域','未選択'],['総合リスク・信頼度','未判定・未校正'],['初観測・最終更新','未取得']],
      '観測事実':[['元観測・出典','未取得'],['発生／観測／公開時刻','未取得'],['受信／適用時刻','未取得・未適用'],['改訂元・共通上流','未照合']],
      '影響分析':[['発生・拡散予測','未算出'],['影響地域・二次的摩擦','未算出'],['誤差・不確実性','未校正']],
      '対応状況':[['判断・元要求','未選択'],['送信／相手側受信','未接続・未確認'],['実行結果／結果観測','未確認・未取得'],['正当な実行権限','未検証']],
      '関連情報':[['国家・企業・組織','未選択'],['関連データ・根拠','未取得'],['参照版・履歴','未照合']]
    };
    p.append(node('h3',tab),rows(content[tab]),node('p','表示タブの切替だけです。参照画像の感染事例・国名・人数・信頼度は転記しません。','quiet'));return p;
  };
  const report=()=>{
    const p=panel('毎時世界状況レポート｜実生成なし','report-panel');
    p.append(rows([['最終生成時刻','未生成'],['対象期間・世界版','未確定'],['根拠の観測時刻','未取得'],['トピック件数','未取得']]));
    p.append(node('h3','地域で絞り込む'),controls(['すべて','アジア','ヨーロッパ','北米','南米','アフリカ','中東','オセアニア'],screen.snapshot().reportRegion,value=>{screen.setRegion(value);rerender('report');},'レポート表示地域'));
    const clear=node('button','フィルタをすべてクリア');clear.type='button';clear.dataset.focusKey='report-filter-clear';clear.addEventListener('click',()=>{screen.clearReportFilters();rerender('report');focusKey('report-filter-clear');});p.append(clear,node('h3','カテゴリで絞り込む'));
    p.append(controls(['すべて','地政学','経済','自然災害','社会・制度','資源・物流','感染症'],screen.snapshot().reportCategory,value=>{screen.setCategory(value);rerender('report');},'レポート表示カテゴリ'));
    p.append(node('p','表示地域：'+screen.snapshot().reportRegion+'／カテゴリ：'+screen.snapshot().reportCategory+'｜絞込み対象データは未取得','quiet'));
    const table=node('table');const head=node('tr');for(const text of ['対象時間帯','カテゴリ・見出し','根拠・生成状態','詳細'])head.append(node('th',text));table.append(head);
    const row=node('tr');for(const text of ['未確定','未取得','実観測・演算・根拠の照合が未成立'])row.append(node('td',text));const detailCell=node('td');const detailButton=node('button','未生成の詳細状態');detailButton.type='button';detailButton.dataset.focusKey='report-detail-open';detailButton.addEventListener('click',()=>{screen.openReportDetail();rerender('detail');focusKey('report-detail-heading');});detailCell.append(detailButton);row.append(detailCell);table.append(row);
    const scroll=node('div',undefined,'table-scroll');scroll.tabIndex=0;scroll.setAttribute('role','region');scroll.setAttribute('aria-label','世界状況レポート表');scroll.append(table);p.append(scroll);
    p.append(node('p','表示選択だけです。毎時生成・取得は稼働していません。未取得を0件や平常とは表示しません。','quiet'));const b=node('button','更新（生成条件未成立）');b.type='button';b.disabled=true;p.append(b);return p;
  };
  const risk=()=>{
    const p=panel('シナリオ別リスク・相互作用｜未算出','risk-structure-panel');const grid=node('div',undefined,'risk-grid');
    for(const title of ['実行した未来','非実行の未来','別選択の未来']){const c=node('section',undefined,'risk-column');c.append(node('h3',title));for(const category of ['物理・エネルギー','資源・物流','経済・制度','社会・生活'])c.append(node('p',category+'：未算出'));grid.append(c);}
    p.append(grid,node('p','反応・外乱・因果経路と比較指標は未確定です。架空の因果矢印や順位は表示しません。','quiet'));return p;
  };
  const related=()=>{const p=panel('関係主体・改訂履歴｜未照合','related-detail-panel');p.append(rows([['国家・企業・組織/主体ID','未選択'],['主体の情報範囲・閲覧権限','未検証'],['元事象・元レポート版','未取得'],['関連するRAW・根拠・改訂理由','未照合'],['元版/過去版の保全','未接続']]),node('p','参照先と閲覧認可を検証できないため、非公開の根拠や内部保存APIへのリンクは表示しません。','quiet'));return p;};
  const detailSummary=()=>{const p=panel(screen.snapshot().reportDetail?'レポート詳細｜本文未生成':'対象事象｜未選択','detail-summary');p.append(rows([['事象ID・レポート版','未取得'],['初観測・最終更新','未取得'],['総合リスク','未判定'],['信頼度・不確実性','未校正']]),node('p','実際の事象は選択されていません。危険の確定・無事件・正常状態とは判定しません。','quiet'));return p;};
  const detailNavigation=()=>{const p=node('nav',undefined,'detail-navigation panel');p.setAttribute('aria-label','事象詳細の表示');p.append(controls(['概要','観測事実','影響分析','対応状況','関連情報'],screen.snapshot().detailTab,value=>{screen.setDetail(value);rerender('detail');},'事象詳細タブ'));return p;};
  return {detail,detailNavigation,detailSummary,related,report,risk};
};
