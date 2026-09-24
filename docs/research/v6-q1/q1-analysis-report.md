# Q1 A/B比較分析（原本freeze後）

原本は `q1-original-freeze-manifest.json` に固定した。A/BはTURN 13・DAY 91で完了。

## 判定

保存されたcheckpoint・raw response・監査記録から、今回の分析ではV6本体の確定BUGは確認できなかった。HTTP 503/402は外部API状態であり、World仕様のBUGとは分類しない。

|観点|分類|現時点の所見|
|---|---|---|
|A/B最初の分岐|HYPOTHESIS|Leader応答差が最初の候補。因果は単一Q1では断定しない。|
|Leader判断差|EMERGENT_RESULT候補|実Gemini応答の差として保存。良否や一般則は未断定。|
|外交・関係|HYPOTHESIS|差分が後続状態へ伝播した可能性はあるが、因果断定不可。|
|制度・承認|HYPOTHESIS|pending/承認系列は分析対象。追加実験なしでは一般化不可。|
|契約・履行|HYPOTHESIS|差分候補はあるが、Q1一回のみでは再現性不明。|
|資源・物流・到着・実利用|HYPOTHESIS|到着・利用履歴を比較対象として保持。|
|物理World State|HYPOTHESIS|A/B状態差は比較可能だが、因果は未確定。|
|人間生活・社会経済|HYPOTHESIS|Metric差は次実験で再確認が必要。|
|回復・脆弱性・bottleneck|MODEL_GAP|13TURNでは長期回復・right-censorの十分な観測窓がない。|
|TURN跨ぎ因果|MODEL_GAP|親差分の機械的追跡情報が全rawに揃わず、時間順だけでは因果を確定できない。|
|創発現象|EMERGENT_RESULT候補|観測された行動は維持し、不具合として修正しない。|
|不自然・無効挙動|BUG未確定|今回の証拠だけでは仕様違反を確定できない。|
|機能しなかった既存機能|BUG未確定|外部API停止とWorld機能を混同しない。|

## 更新候補

|区分|内容|
|---|---|
|そのまま維持|Q1原本、A/B条件、World、Action schema、観測記録、checkpoint。|
|V6.1修正候補|今回確定BUGなし。usage metadataの即時保存は既存修正として維持。|
|V7研究仕様候補|長期回復・因果識別・再現性評価を複数Q1で検証する設計。|
|次実験で検証|A/B差分の再現、Leader判断差の伝播、契約・物流・実利用への影響。|

TURN 6 raw responseが通常raw配下にないため、完全なTURN別raw比較はfreeze manifest内のarchive/provenanceを参照する。これは分析上の証拠制約であり、World状態のBUGとは分類しない。
