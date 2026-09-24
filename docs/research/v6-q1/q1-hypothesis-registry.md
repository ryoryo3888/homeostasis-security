# Q1 Hypothesis Registry

対象：freeze済みQ1原本と`q1-analysis-report.md`のみ。追加API・追加実験・V6変更は未実施。

## H-001：A/B差分の伝播候補

- **Observation**：Q1ではA/B両WorldがTURN 13・DAY 91まで完走し、Leader応答・状態履歴・Metricが保存された。具体的な因果差はQ1単独では確定していない。
- **First Divergence**：Q1原本から、最初の分岐候補をLeader応答差として追跡可能。ただし確定TURN・Action・World Stateの因果起点は未確認。
- **Propagation Chain**：判断→外交→制度→契約→資源→物流→到着→利用→World Mutation→Metricの各段階は保存対象だが、全段階を一続きの因果経路として確定できない。
- **Outcome**：TURN 13時点のA/B差は比較対象として保存済み。差の原因は未確定。
- **Competing Explanation**：Leader応答の偶然差、初期条件・seedの影響、制度・契約・物流の遅延差、外部API応答差。
- **Current Classification**：HYPOTHESIS
- **Falsifiable Hypothesis**：同一初期条件でseedを変えた複数paired runでも、同じ層の差分が再現しなければ、Q1で見えた差は固有の創発構造とは支持されない。
- **Required Replication**：seed変更＋A/B反転。必要に応じて52TURNへ長期化。
- **Evidence Strength**：Q1内で差分の存在は比較可能、経路証拠は部分的、因果は未確認。

## H-002：短期観測では回復・bottleneckを識別できない

- **Observation**：13TURNでは長期回復、right-censored、累積不足、bottleneckの十分な観測窓が不足。
- **First Divergence**：未確認。
- **Propagation Chain**：回復関連の一続きの伝播は未確認。
- **Outcome**：TURN 13時点で回復差を一般化できない。
- **Competing Explanation**：観測期間不足、イベント発生時点の差、資源・物流遅延。
- **Current Classification**：HYPOTHESIS
- **Falsifiable Hypothesis**：52TURN継続で回復判定が成立しない場合、13TURNでの回復差仮説は支持されない。
- **Required Replication**：長期化（52TURN以上）＋seed変更。
- **Evidence Strength**：未確認。

## 最小追加実験群

同一のpaired実験でH-001とH-002を同時検証する。必要条件は、複数seed、A/B反転、52TURN継続、層別差分記録。現時点では設計のみで、実行していない。
