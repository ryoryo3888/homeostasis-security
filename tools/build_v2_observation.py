"""Build a read-only V2 result page while leaving all frozen dashboards untouched."""
from __future__ import annotations

from html import escape
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'results/v2-five-runs'
ACTORS = ('A', 'B', 'C', 'COORDINATOR')
LABELS = {'A': 'A国', 'B': 'B国', 'C': 'C国', 'COORDINATOR': '地球調整機関'}
SUMMARIES = [
    '第4ターンに各国の承認表明と調整機関の成立宣言が現れた。全員が第8ターンまで発言を送信した。B国は初回だけ宛先を2組に分け、その後は他の3者へ同じ発言を送っている。',
    '第4ターンに承認表明と成立宣言が現れた。B国は第7ターンに発言を送信せず、第8ターンには送信を再開した。送信がないターンも正常な判断記録として残っている。',
    '第4ターンに承認表明と成立宣言が現れた。調整機関は第6ターンから送信せず、第7・8ターンは全員が送信しなかった。8ターンすべての判断処理は完了している。',
    '第3ターンに各国の草案承認と調整機関の協定確定宣言が現れた。他の回より早い段階で、対話上の協定確定が語られた。第8ターンは全員が発言を送信しなかった。',
    '第4ターンに各国の承認表明と調整機関による実務協議体の発足宣言が現れた。B国は全8ターンでA国・地球調整機関・C国へ別々の発言を送り、相手ごとに内容を変えている。',
]


def turn_markup(trial, turn):
    records = [m for m in trial['messages'] if m['sent_round'] == turn]
    quiet = [LABELS[a] for a in ACTORS if not any(m['sender'] == a for m in records)]
    note = f'このターンは{len(records)}通の発言を送信。'
    note += '送信なし：' + '・'.join(quiet) + '。' if quiet else '4者とも発言を送信した。'
    note += '各参加者は前ターンまでの自分宛ての発言を参照している。同じターンの相手の発言を読んで返答した記録ではない。'
    if turn == 8:
        note += 'ここで観測期間が終了。第8ターンの発言への次ターンの反応は未観測。'
    parts = [f'<section class="record-turn" data-trial="{trial["trial"]}" data-round="{turn}">',
             f'<h2>第{trial["trial"]}回・第{turn}ターン</h2>',
             '<aside class="evaluation"><b>AIによる観測解説（実験後に作成）</b>',
             f'<p>{escape(note)}</p></aside>']
    for actor in ACTORS:
        messages = [m for m in records if m['sender'] == actor]
        parts += [f'<article class="agent panel transcript" data-actor="{actor}"><h3>{LABELS[actor]}｜発言の原文</h3>']
        if not messages:
            parts.append('<p class="silent">送信した発言：なし（判断処理は完了）</p>')
        for message in messages:
            recipients = '・'.join(LABELS[x] for x in message['to'])
            mid = f'run-{trial["trial"]}-{message["id"]}'
            parts += [f'<section class="message" id="{escape(mid, quote=True)}">',
                      f'<p class="message-meta">送信先：{recipients} ／ 第{message["available_round"]}ターンから相手の入力に含まれる</p>']
            if 'reply_to' in message:
                parts.append(f'<p class="message-meta">返信先記録：{escape(str(message["reply_to"]))}</p>')
            parts += [f'<blockquote data-message-id="{escape(message["id"], quote=True)}">{escape(message["body"])}</blockquote>', '</section>']
        parts.append('</article>')
    return '\n'.join(parts + ['</section>'])


def build_html(source, data):
    # Reuse existing visual rules and Earth subtree verbatim; exclude historical
    # research copy/CSS which asserts the old deterministic recovery experiment.
    styles = re.findall(r'<style>.*?</style>', source, re.S)
    if len(styles) != 5 or 'V2 Earth System Field' not in styles[3]:
        raise ValueError('Frozen source shape changed; review required')
    earth = re.search(r'    <section class="earth-panel panel">.*?    </section>', source, re.S).group()
    styles = '\n'.join(styles[i] for i in (0, 1, 3, 4))
    countries = ''.join(f'<article class="agent panel {a.lower()}"><h2>{LABELS[a]}</h2><p class="role">{escape(data["initial"]["roles"][a])}</p><div class="action" id="count-{a}">記録を読み込み中</div><div class="response" id="to-{a}"></div><p><a class="record-link" href="#records">原文を読む ↓</a></p></article>' for a in ACTORS[:3])
    run_options = ''.join(f'<option value="{n}">第{n}回</option>' for n in range(1, 6))
    turn_buttons = ''.join(f'<button type="button" class="turn-button direct" data-turn="{n}">{n}</button>' for n in range(1, 9))
    summaries = ''.join(f'<article class="agent panel"><h3>第{n}回 · {len(t["messages"])}通</h3><p>{escape(SUMMARIES[n-1])}</p></article>' for n, t in enumerate(data['trials'], 1))
    transcripts = '\n'.join(turn_markup(t, turn) for t in data['trials'] for turn in range(1, 9))
    initial = escape(json.dumps(data['initial'], ensure_ascii=False, indent=2))
    return f'''<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<base href="../../"><title>HOMEOSTASIS SECURITY v2｜5回の自由対話・観測記録</title>
{styles}
<link rel="stylesheet" href="results/v2-five-runs/observation.css">
<script defer src="results/v2-five-runs/observation.js"></script>
</head><body><main class="shell">
<section class="mast">
  <div class="brand panel"><div class="brand-en">HOMEOSTASIS SECURITY v2</div>
    <h1>地球規模の恒常性シミュレーション</h1><p>保存済みの自由対話実験｜同じ初期条件から、どんな対話や関係が生まれたか</p>
    <div class="experiment-meta"><span>Gemini Agent 実験結果</span><span>5回／各8ターン</span><span>A国・B国・C国・地球調整機関</span><span>gemini-3.6-flash</span></div>
    <nav class="version-switch" aria-label="バージョン切替"><a href="dashboard_v1.html">v1：二国間の恒常性</a><a href="results/v2-five-runs/index.html" class="active" aria-current="page">v2：地球規模の恒常性</a></nav>
  </div>
  <div class="origin panel"><div><b>発生元</b><strong>V2独立シナリオの初期事象</strong></div><div class="event"><b>事件</b><strong>A国のミサイルがB国の民間農地へ着弾</strong></div><div class="impact"><b>初期被害</b><strong>年間8,000tの米生産能力を喪失</strong></div><div class="flow">自由に発言・提案 <span>→</span> 相手の反応を観測 ／ 物理的な復旧量は未測定</div></div>
</section>
<section class="controls panel" aria-label="観測記録の操作"><div class="turn-operations"><label for="trialSelect">実験 <select id="trialSelect">{run_options}</select></label><div class="turn-label"><span class="control-heading">SIMULATION CONTROL</span><strong id="turnNumber">1</strong> / 8</div><div class="turn-buttons"><button class="turn-button nav-button" id="prevTurn" type="button">‹ 前へ</button>{turn_buttons}<button class="turn-button nav-button" id="nextTurn" type="button">次へ ›</button></div></div><div class="event-now" id="selectionStatus" role="status" aria-live="polite">保存された実験記録を表示。操作による追加実験・API通信はありません。</div></section>
<section class="hero"><div class="agent-stack" id="agents">{countries}</div>
{earth}
<aside class="coordinator panel"><h2>地球調整機関</h2><div class="role">強制権を持たない地球調整機関</div><div class="proposal" id="count-COORDINATOR"></div><div class="proposal-reason" id="to-COORDINATOR"></div><p><a class="record-link" href="#records">原文を読む ↓</a></p><div class="evaluation"><b>観測範囲</b><p>発言・宛先・送信しなかった判断を保存。協定成立や支援実施は、発言者の主張として読む。</p></div><div class="damage"><b><span>農地被害の残存</span><span>未測定</span></b><p><small>活動要求は全回0件。発言だけから復旧量・輸送量・資源変化を計算していない。</small></p></div></aside></section>
<h2 class="section-title">GLOBAL STATE｜今回の実験における世界の変化</h2><section class="metrics">{''.join(f'<div class="metric panel"><span>{name}</span><strong>未測定</strong></div>' for name in ('食料','経済','エネルギー','環境','国際的信用','紛争負荷'))}</section>
<section id="records" class="observation panel"><h2>発言の原文と、ターンごとの観測</h2><p class="scope">宛先に含まれる参加者だけに発言を配信。この画面では観測者として全宛先の発言を確認できます。自分用メモ・モデル内部の思考は掲載していません。</p><p class="scope">AIによる観測解説は実験後に作成し、Agentには渡していません。輸送・復旧・市場などに関する発言は、世界で実行されたことの確認ではありません。</p><noscript><p>JavaScriptが無効のため全40ターンを続けて表示しています。</p></noscript>{transcripts}</section>
<section class="observation panel"><h2>5回の比較</h2><p class="scope">AIによる観測解説（実験後に作成）</p><div class="comparison">{summaries}</div><p>5回とも対話は協力・合意を語る方向へ進んだ。その中で、宛先の分け方や発言を続ける期間には違いが現れた。ここで確認できるのは対話上の違いであり、物理的な復旧や制度の履行ではない。</p><p>同じターンの承認表明と成立宣言は、それぞれ前ターンまでの情報に基づく発言。同じターンに互いの承認を確認したとは限らない。</p><p>1条件を5回繰り返した予備観測。初期役割・事件・数値の影響や、別条件での再現性・創発そのものの証明までは確かめていない。第8ターン後の経過は未観測。</p><details><summary>実験条件と保存記録</summary><p>各回は初期状態から開始し、前の回の対話や観測解説を引き継いでいない。追加の事件は与えていない。シードの指定は行っていない。</p><p>{escape(data['operational_difference'])}</p><p>以下の数値は既存の初期条件。今回の対話に伴う変化を測定した値ではない。</p><pre>{initial}</pre><a href="results/v2-five-runs/data.json">発言の原文・宛先・記録IDを含む保存データ</a></details></section>
<p class="observation"><a href="dashboard_v2.html">以前のV2観測記録（1回・5ターン）を開く</a></p>
</main></body></html>\n'''


def main():
    data = json.loads((OUTPUT / 'data.json').read_text())
    (OUTPUT / 'index.html').write_text(build_html((ROOT / 'dashboard_v2.html').read_text(), data))
    print('V2 observation page built; frozen dashboards unchanged.')


if __name__ == '__main__':
    main()
