/* Saved text only: no model, simulation, telemetry or network calls. */
(() => {
  'use strict';
  const actors = ['A', 'B', 'C', 'COORDINATOR'];
  const labels = {A:'A国', B:'B国', C:'C国', COORDINATOR:'地球調整機関'};
  const sections = [...document.querySelectorAll('.record-turn')];
  const select = document.querySelector('#trialSelect');
  let trial = 1, turn = 1;
  const recordURL = new URL('results/v2-five-runs/index.html', document.baseURI);
  const text = (id, value) => {document.getElementById(id).textContent = value};
  function render(updateURL = true) {
    select.value = String(trial);
    text('turnNumber', turn);
    text('sovereignty', '未測定'); text('homeostasis', '未測定');
    const active = sections.find(s => +s.dataset.trial === trial && +s.dataset.round === turn);
    sections.forEach(s => {s.hidden = s !== active});
    for (const actor of actors) {
      const article = active.querySelector(`[data-actor="${actor}"]`);
      const count = article.querySelectorAll('[data-message-id]').length;
      text('count-' + actor, count ? `このターンの送信：${count}通` : 'このターンの送信：なし');
      text('to-' + actor, '判断記録あり ／ 原文は下の記録へ');
      const link = document.querySelector(actor === 'COORDINATOR' ? '.coordinator .record-link' : `.agent.${actor.toLowerCase()} .record-link`);
      link.href = recordURL.pathname + recordURL.search + `#run=${trial}&turn=${turn}&actor=${actor}`;
      link.onclick = e => {e.preventDefault();article.scrollIntoView({block:'start'});history.replaceState(null, '', link.href)};
      article.style.scrollMarginTop = '110px';
    }
    document.querySelectorAll('[data-turn]').forEach(button => {
      button.classList.toggle('active', +button.dataset.turn === turn);
      button.setAttribute('aria-pressed', String(+button.dataset.turn === turn));
    });
    document.getElementById('prevTurn').disabled = turn === 1;
    document.getElementById('nextTurn').disabled = turn === 8;
    text('selectionStatus', `第${trial}回・第${turn}ターン ／ 保存記録を表示中。追加のAPI通信なし。`);
    if (updateURL) history.replaceState(null, '', recordURL.pathname + recordURL.search + `#run=${trial}&turn=${turn}`);
    document.body.dataset.observationReady = 'true';
  }
  function fromURL() {
    const params = new URLSearchParams(location.hash.slice(1));
    const bounded = (value, max) => /^\d+$/.test(value || '') && +value >= 1 && +value <= max ? +value : 1;
    trial = bounded(params.get('run'), 5); turn = bounded(params.get('turn'), 8);
    render(false);
    if (actors.includes(params.get('actor'))) {
      sections.find(s => !s.hidden).querySelector(`[data-actor="${params.get('actor')}"]`).scrollIntoView({block:'start'});
    }
  }
  select.addEventListener('change', () => {trial = +select.value;turn = 1;render()});
  document.querySelectorAll('[data-turn]').forEach(button => button.addEventListener('click', () => {turn = +button.dataset.turn;render()}));
  document.getElementById('prevTurn').addEventListener('click', () => {turn = Math.max(1, turn - 1);render()});
  document.getElementById('nextTurn').addEventListener('click', () => {turn = Math.min(8, turn + 1);render()});
  addEventListener('hashchange', fromURL);
  fromURL();
})();
