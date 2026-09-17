# 8TURN run #2: mixed-channel receiver capacity failure

対象: `20260917T071205Z-fb7f949f`。この解析・修正はAPI 0。原本・研究結果は変更しない。
機械可読一次情報: [diagnosis](../../results/status/diagnostics/20260917T071205Z-failure-diagnosis.json)。

## 証拠と正確な故障箇所

29回のdurable transport attemptすべてがreturned / sdk_returned。retry 0、TURN1・2完了。
24国家回答・3調整機関回答・2Evaluator回答はすべてdecision validation PASS。
SMALLはTURN3の最後の回答者で、故障Agentではない。既存public failure.agent_idは最後のcallからの推定であり、例外発生主体を示さない。
保存されたfailure.jsonには例外メッセージや行番号がないため、実行元5961924のfeasibility.pyを読み込み、保存済み状態と行動で再現した。

`apply_structured_actions` → `settle_atomic_actions` → 旧feasibility.py:129:
`ValueError: atomic settlement produced an out-of-range resource`。
条件評価・構造化回答validation・choice materializationは通過済み。Evaluator呼出しの前に資源不変条件で停止した。
原本のcompleted_turnは2のままで、部分的なTURN3世界状態が研究結果へ反映された証拠はない。関数は入力をcopyして処理する。

SMALLはCONDITIONAL、A003、amount 10。Python復元はPROVIDE_RESOURCE / world_pool / food / 10。
required_countries=[FOOD,ECON]、maximum_sovereignty_burden=30、mutual_performance=true、自己burden=28。
この回答も他7国家も契約上有効で、同時条件集合は全8国家。公開理由はfixture・診断JSONに原文のまま保存する。

## 根本原因

FRAGILEの開始logisticsは34.8、受入余地65.2、開始pool logisticsは100。
FOODのpool引出し20、FRAGILE自身のpool引出し65.2、MILの直接援助5が同じ受取国・資源へ向かう。
旧処理はpool引出しだけを65.2へ縮小し、直接援助5には別の受入余地65.2を与えた。
結果は34.8+65.2+5=105。合法な個別行動を合成する決済器が受入制約を二重計上した。
TURN3のderived event「物流・配分競合」や履歴は有効。後続TURNでpoolと直接援助が共存したことが露呈条件であり、特定TURNやSMALL固有ではない。

旧単一TURNの開始poolは空。既存atomic property testはpool引出し同士を中心に検証し、直接援助との混合制約を覆っていなかった。
以前の保存回答replayも、その回答集合に混合容量競合がなければ検出できない。schema PASSは集約資源制約の充足を保証しない。

## 汎用修正と限界

1. 開始pool stockで引出し候補を比例制限。
2. 直接援助とpool引出しを同じreceiver/resourceの組に集め、開始受入余地で一括比例制限。
3. 確定した引出し量だけpoolを減らし、その後に同時拠出を追加。
4. 全deltaをatomicに適用し、既存の上限・下限guardを維持。

同じTURNの拠出で引出しを賄わず、送出でできた受入余地も同じTURNでは再利用しない。
受入制限で解放されたpool量を他の要求へ再配分する最大流最適化は行わない。既存の保守的な開始状態・比例配分方針を維持する。
順序で優先順位を変えず、Agent回答・choice-ID・条件・strict validationを変更しない。

追加の境界検証で、feasible maximumを8桁へ丸める際に実在庫を最大約5e-9上回る不具合も発見。
実際の上限floatをそのままカタログへ渡し、合法な最大量で送出在庫が負になる経路を防いだ。許容誤差を拡大する対応はしない。

## Counterfactual replay（研究結果ではない）

保存済みTURN1・2のworld/settlement/reconstruction/Evaluator入力は修正版で完全一致。
TURN3では3要求90.2に共通scale=65.2/90.2を適用:
MIL=3.614190687361419、FOOD=14.456762749445677、FRAGILE=47.12904656319291。
決済直後FRAGILE logistics=100、pool logistics=38.41419068736141。
資源ネットワーク・world計算・reconstructionまで例外なく処理可能。
復興後damage=6163.5352（counterfactual、実runの結果ではない）。
未取得のTURN3 Evaluator回答は作らない。従って実runは2TURN完了の失敗runのまま。

9件の追加テスト: 全24国家回答のstrict再parse、TURN1/2完全照合、TURN3全40320順序のatomic一致と完全effects逆順一致、7資源×受取4境界×pool4境界、200の生成合法最大量集合、fractional上限、過剰送出fail-closed、原本hash不変、合成TURN4〜8の状態連鎖。
TURN4〜8の合成入力はテスト用で、モデル判断や実runの続きを推定するものではない。全連続状態・全モデル出力の数学的網羅保証ではない。

## 次段階の判断

checkpoint resumeは正式研究として推奨しない。旧決済コードで得た履歴と新決済コードを混在させ、失敗地点を見て介入した系列になる。TURN3のEvaluatorも未取得で、単純resumeは既存29試行を正しく扱う検証済み研究手順ではない。
失敗runは隔離を維持し、replayを開発証拠として保存する。

無料check・publication gate・CIがPASSした固定ソースから、別途明示許可後に新run_idで8TURNを1世界線、最大80 calls、retry 0、最初の不正回答／invariant失敗で即停止することを推奨。
新1-call probeや1TURNは今回の混合資源状態を再現せず、既に29回答で確認されたtransportを繰り返すため追加の有料入口検証は不要。
1世界線の完走だけで一般的研究結論を断定せず、完走時だけ既存research eligibilityを検証する。
