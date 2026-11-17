"use strict";
(() => {
  const state = new globalThis.HS_VISUAL_STATE();
  const stage = document.getElementById('layout-columns');
  const geography = document.querySelector('.geographic-layout');
  const globeVisual=document.getElementById('globe');const mapVisual=document.getElementById('map');
  let secondaryViewport=null;
  const heading = document.getElementById('view-heading');
  const message = document.getElementById('view-message');
  const swap = document.getElementById('swap-view');
  const titles = {normal:'通常監視',emergency:'緊急判断',comparison:'3未来の比較',
    'comparison-detail':'分岐条件の詳細比較',crisis:'世界俯瞰・危機分析',map:'世界地図メイン',
    globe:'地球儀メイン',report:'世界状況レポート',detail:'個別事象詳細'};
  let layout = 'normal';
  const screen = new globalThis.HS_SCREEN_STATE();
  const timeDisplay = globalThis.HS_TIME_DISPLAY();
  const monitoringPanels = globalThis.HS_MONITORING_PANELS();
  const emergencyPanels = globalThis.HS_EMERGENCY_PANELS();
  const detailPanels = globalThis.HS_DETAIL_PANELS(screen,key=>render(key));
  const node = (tag, text, className) => {
    const element = document.createElement(tag); if (text !== undefined) element.textContent = text;
    if (className) element.className = className; return element;
  };
  const panel = (title, cls = '') => {const element=node('section',undefined,'panel layout-panel '+cls);element.append(node('h2',title));return element;};
  const rows = (items) => {const list=node('dl');for(const [name,value] of items){list.append(node('dt',name),node('dd',value));}return list;};
  const frameInfo = () => {const list=rows([['運用基準','日本・日本語'],['ライブ・再生・シミュレーション','表示未接続（世界稼働の判定ではありません）'],['世界時間','未初期化'],['世界版','未確定'],['表示時点・観測締切','未確定'],['入力由来','未取得・未検証'],['基準世界の同一性','未検証'],['端末時計の同期精度','未検証（観測時刻ではありません）']]);timeDisplay.appendClocks(list);return list;};
  const unready = text => node('p',text,'quiet');
  const disabled = label => {const button=node('button',label);button.type='button';button.disabled=true;return button;};
  const timeline = () => timeDisplay.timeline(layout);
  const sourcePanel = () => {const element=panel('観測・由来・不確実性','source-panel');element.append(rows([['地球状態の現実観測','未取得'],['推定状態','未算出'],['世界内部状態','未初期化'],['物理的変化','未適用'],['利用権・更新時刻','未照合']]),unready('欠損・未観測を正常・無事件・ゼロとして表示しません。'));return element;};
  const metrics = () => {const element=panel('主要指標','metrics-panel');element.append(rows([['電力・エネルギー','未取得／単位未確認'],['物流・資源','未取得／単位未確認'],['通信・経済','未取得／単位未確認'],['社会・制度','未取得／尺度未校正'],['その他の指標','未算出・未校正']]));return element;};
  const branches = () => {
    const element=panel('選択に対する3未来｜すべて未演算','branch-section');
    const grid=node('div',undefined,'branch-grid');
    for(const title of ['選択を実行した未来','その選択を実行しなかった未来','別の選択を実行した未来']){
      const card=node('article',undefined,'branch-card');card.append(node('h3',title),rows([['実行ID・分岐ID','未発行'],['選択・前提','未指定'],['対象時間範囲','未確定'],['物理的帰結','未算出'],['周辺への二次的摩擦','未算出'],['予測の信頼度・誤差','未校正']]),disabled('詳細条件（未接続）'));grid.append(card);
    }
    const inspect=node('button','比較条件の表示構造を見る');inspect.type='button';inspect.addEventListener('click',()=>{render('comparison-detail');heading.tabIndex=-1;heading.focus({preventScroll:true});});
    element.append(grid,inspect,unready('同じ条件での未来比較は未成立です。継続動作も未検証です。'));return element;
  };
  const layerPanel = () => {
    const element=panel('表示レイヤー｜データは未取得','layer-panel');
    for(const layer of ['観測','推定','世界内部状態','物理的変化']){
      const label=node('label');const input=node('input');input.type='checkbox';input.checked=state.snapshot().layers.includes(layer);
      input.addEventListener('change',()=>{state.setLayer(layer,input.checked);renderContext();});label.append(input,node('span',layer));element.append(label);
    }
    element.append(unready('地球儀と地図で同じ表示選択を使います。選択はデータ取得・世界更新を意味しません。'));
    const spaces=node('details',undefined,'space-controls');spaces.append(node('summary','7空間の表示範囲｜取得未成立'));
    const fields=node('fieldset');fields.append(node('legend','表示対象空間（世界の取得済み範囲ではありません）'));
    for(const space of ['陸上','海面','水中','大気','地下','地質','宇宙']){
      const label=node('label');const input=node('input');input.type='checkbox';input.checked=state.snapshot().spaces.includes(space);
      input.addEventListener('change',()=>{state.setSpace(space,input.checked);renderContext();});label.append(input,node('span',space));fields.append(label);
    }
    spaces.append(fields,unready('空間の表示選択だけです。実データ・3次元位置・空間間の関係は未接続で、配置確認用の図形は描き分けません。'));element.append(spaces);return element;
  };
  const geographyPanel = () => {const element=panel(layout==='normal'?'地理表示｜過去の衛星合成・表示確認用':'地理表示｜配置確認用','geography-panel');element.append(geography);return element;};
  const secondaryGeographyPanel=()=>{const element=panel('地理サブ表示｜配置確認用','secondary-geography-panel');secondaryViewport=node('div',undefined,'secondary-geographic-viewport');element.append(secondaryViewport);return element;};
  const comparisonTable = () => {
    const element=panel('比較指標・同一条件の照合','comparison-table-panel');
    const table=node('table');const head=node('tr');for(const text of ['比較項目','実行','非実行','別選択'])head.append(node('th',text));table.append(head);
    for(const name of ['基準世界・締切','評価方式・指標','比較期間','世界全体への影響','二次的摩擦・負荷']){const row=node('tr');row.append(node('th',name));for(let i=0;i<3;i++)row.append(node('td','未確定／未算出'));table.append(row);}
    const scroll=node('div',undefined,'table-scroll');scroll.tabIndex=0;scroll.setAttribute('role','region');scroll.setAttribute('aria-label','比較条件表（狭い画面では横にスクロール）');scroll.append(table);const controls=node('div',undefined,'table-controls');for(const [label,direction] of [['表の左側',-1],['表の右側',1]]){const button=node('button',label);button.type='button';button.addEventListener('click',()=>scroll.scrollBy({left:direction*table.rows[0].cells[1].getBoundingClientRect().width,behavior:'instant'}));controls.append(button);}element.append(controls,scroll,unready('狭い画面では表を横にスクロールできます。比較値は未算出です。'));return element;
  };
  const comparisonContext = () => {const p=panel('比較の共通条件と変更条件｜未設定','comparison-context-panel');p.append(rows([['起点世界・観測入力の集合/版','未確定・未照合'],['比較設定の版','未対応づけ'],['共通期間・評価方式・指標','未確定'],['意図的に変更する条件','未指定'],['生成条件','未対応づけ'],['観測済みの物理的変化','未取得'],['因果関係の候補','未分析・未確認']]),unready('保存済み比較は未接続です。条件の表示は比較実行・候補採用を意味せず、ライブの新規観測も取り込みません。'));return p;};
  const reportPanel = () => detailPanels.report();
  const detailPanel = () => detailPanels.detail();
  const renderContext = () => {
    const snapshot=state.snapshot();
    if(secondaryViewport){geography.append(snapshot.primary==='globe'?globeVisual:mapVisual);secondaryViewport.append(snapshot.primary==='globe'?mapVisual:globeVisual);}else{geography.append(globeVisual,mapVisual);}
    document.getElementById('globe').className='visual '+(snapshot.primary==='globe'?'primary':'secondary');
    document.getElementById('map').className='visual '+(snapshot.primary==='map'?'primary':'secondary');
    swap.textContent=snapshot.primary==='globe'?'地図を主表示にする':'地球儀を主表示にする';
    const label='世界版：未確定／表示時点：未確定／レイヤー：'+(snapshot.layers.join('・')||'選択なし')+'（データ未取得）';
    for(const id of ['globe-context','map-context','frame-context'])document.getElementById(id).textContent=label;
    const scope='表示対象：'+(snapshot.spaces.join('・')||'選択なし')+'｜全空間の取得状態は未成立';
    for(const id of ['globe-scope','map-scope'])document.getElementById(id).textContent=scope;
  };
  const render = key => {
    if (!Object.hasOwn(titles,key)) return;
    layout=key;secondaryViewport=null;geography.classList.toggle('separated-primary',['map','globe'].includes(key)); document.body.dataset.layout=key;heading.textContent=titles[key];
    state.setPrimary(['map','detail','report'].includes(key)?'map':'globe');
    // Keep the same two geographic nodes and one display state across all layouts.
    const holding=document.createDocumentFragment();holding.append(geography);stage.replaceChildren();
    const left=key==='emergency'?emergencyPanels.request():panel('現在の参照条件','reference-panel');
    if(key!=='emergency')left.append(frameInfo());
    if(key==='report')stage.append(left,reportPanel(),geographyPanel(),metrics(),sourcePanel());
    else if(key==='detail')stage.append(detailPanels.detailSummary(),detailPanels.detailNavigation(),detailPanel(),geographyPanel(),sourcePanel(),timeline(),detailPanels.related());
    else {
      stage.append(left,geographyPanel());
      if(['map','globe'].includes(key))stage.append(secondaryGeographyPanel());
      stage.append(key==='emergency'?emergencyPanels.authority():metrics());
      if(key==='emergency')stage.append(emergencyPanels.history());
      stage.append(layerPanel());
      if(['comparison','comparison-detail','crisis','emergency'].includes(key))stage.append(branches());
      if(['normal','map','globe'].includes(key))stage.append(monitoringPanels.overview());
      if(key==='crisis')stage.append(monitoringPanels.crisis());
      if(['comparison','comparison-detail'].includes(key)){stage.append(comparisonContext());}
      if(key==='comparison-detail')stage.append(comparisonTable(),detailPanels.risk(),timeline());
      else stage.append(sourcePanel(),timeline());
    }
    message.textContent='9画面のレイアウト制作途中です。地理データ・地球状態の実観測・演算表示・予測・認証の接続は未成立で、世界状態は変更しません。各機能は開発・検証の途中です。';
    document.querySelectorAll('[data-layout]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.layout===key)));
    renderContext();timeDisplay.refresh();
  };
  swap.addEventListener('click',()=>{if(['map','globe'].includes(layout))render(state.snapshot().primary==='globe'?'map':'globe');else{state.togglePrimary();renderContext();}});
  document.querySelectorAll('[data-layout]').forEach(button=>button.addEventListener('click',()=>render(button.dataset.layout)));
  render(layout);
  setInterval(()=>timeDisplay.refresh(),1000);
})();
