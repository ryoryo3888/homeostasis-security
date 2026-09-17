# V3 第2段階：8国家・有限資源・需要・能力・収支

承認範囲は物理状態と1TURN相当の無料単体検証のみ。Agent、Coordinator、Evaluator、交渉、取引決済、供給経路探索、ネットワーク波及、閉ループrun、V3 UIは実装・実行しない。

## 実装と入力

- `homeostasis_v3/physical.py`：初期状態validator、純粋なphysical_step、台帳照合、分布と自立性構成要素の取得。
- `scenarios/v3/synthetic_baseline.json`：8国家の合成初期条件。正式ExperimentではなくRegistry未登録。
- `tests/v3/test_physical.py`：無料fixtureによる物理単体検証。結果ファイルや研究worldlineは生成しない。

国家IDは既存系譜のMIL/RES/FOOD/SMALL/ISLAND/ECON/FRAGILE/NEUTRALを安定識別子として維持する。文字列の歴史的意味を将来の役割にしない。国家に役割・善悪・行動傾向・危機予定を設定しない。engineに8という件数制約はなく、1国家のfixtureでも同じ処理を検証する。

## 資源と初期差

有限stockはfoodとenergy。energyは抽象的な保管可能エネルギー量で、発電能力そのものではない。輸送能力と復旧能力は別capacity、物品として供給・消費しない。food/energyの生産capacityも別型で、最大能力・現在能力・稼働率ppmを持つ。

| ID | food stock / 必須需要 / 現在生産 | energy stock / 必須需要 / 現在生産 | 輸送 / 復旧能力 |
| --- | --- | --- | --- |
| MIL | 68 / 18 / 12 | 70 / 22 / 20 | 18 / 10 |
| RES | 72 / 16 / 20 | 96 / 18 / 26 | 16 / 8 |
| FOOD | 42 / 20 / 10 | 58 / 16 / 10 | 14 / 6 |
| SMALL | 58 / 12 / 14 | 48 / 10 / 8 | 10 / 6 |
| ISLAND | 50 / 14 / 18 | 42 / 14 / 20 | 12 / 8 |
| ECON | 75 / 22 / 16 | 65 / 26 / 24 | 20 / 12 |
| FRAGILE | 35 / 15 / 8 | 32 / 12 / 6 | 8 / 4 |
| NEUTRAL | 88 / 16 / 22 | 62 / 16 / 18 | 16 / 10 |

全てモデル単位で、現実国家の統計ではない。food stockとenergy stockの数値的大きさは旧archetypeのfood/fossil_fuelから参照したが、旧scoreを物理量へ換算したものではないため**synthetic_assumption**とする。energyは旧energy合成指数でもない。出典commitとfieldは各値のprovenanceに記録する。

需要・生産・輸送・復旧は合成仮定。物理的な異質性を持つテスト基準として個別設定し、特定TURNの不足・回復を逆算していない。現実への校正も最適化もしていない。最大能力は現在値+4の合成設備余地、初期稼働率は100%。最大値まで自動回復・増強する処理はない。availableはcurrent×ppm/1,000,000の切下げというderived値。

worldとcapacity_profilesの全数値にJSON pointer単位のprovenanceを必須化する。由来種別、出典、短い理由を保存し、欠損・重複・対象外参照を拒否する。外部資料の数値の真偽や校正妥当性をvalidatorが自動証明するわけではない。

生産<需要と生産>需要が両方存在し、全国家の初期stockは最初の必須需要を満たす。従って「全員永久自給」でも「初手全員不足」でもない。ただし供給・回復・崩壊の結末は予測しない。崩壊という状態遷移自体を本段階に持たない。

## 生産・消費の時間境界

既存設計の次TURN可用規則に従い、1単位処理は：

期首stock → 明示された損失 → 必須需要の実消費／不足 → 能力由来の生産を期末stockへ加算 → 収支照合。

生産量=floor(current_capacity×utilization_ppm/1,000,000)。台帳はcapacity IDと規則を参照し、Agent発言を入力にしない。今TURN生産を今TURNの期首消費へ遡って使わない。例：期首70、需要100、生産12なら、実消費70、不足30、期末12。生産0なら期末0。

生産は明示的な外生生産源である。土地・燃料・機械の産業投入モデルはまだ作らず、その省略を各台帳に記載する。これは無根拠な自然増加ではなく、有限の能力上限によるsource項。後続の投入依存追加では規則versionを変える。

通常需要は今回追加せず、全resourceに必須需要を明示。需要0は合法で充足率・備蓄カバーTURN数はnull。未定義需要は0に変換せず拒否する。不足は数量として保持し、勝敗・崩壊・善悪へ変換しない。

## 台帳と検証

各国家/resourceにopening_stock、production、consumption、loss、incoming、outgoing、in_transit、closing_stock、required_demand、fulfilled_demand、unmet_demand、fulfillment_rateと理由参照を記録。

`opening + production + incoming − consumption − outgoing − loss = closing`

`fulfilled + unmet = required`、実消費は存在する期首残高からのみ。数量は非負整数。未知損失口座、過剰損失、能力超過、単位混同、二重口座、需要欠落を拒否する。

移転と輸送を実行しないのでincoming/outgoing/in_transitは0。本段階の実行入力に非ゼロ輸送中口座は受け付けない。汎用distributionでは輸送中を国内stockから除外し別集計し、総量へ一度だけ含める。後段の配送予約や着荷処理を先取りしない。

check_balanceは算術の局所検証。validate_stepは元の初期条件・損失証拠から決定的な期待台帳と末状態を照合し、生成と期末を同時に増やした偽の帳尻合わせも拒否する。入力は変更せず、処理結果は新しいdictとして返す。正式研究runの監査・署名・永続化は後続段階。

## 自律性と自立性

各国のdecision_authority=self、委任・intentは空のまま。国家判断を実装しない。

自立性は国内stock、生産能力、必須需要、備蓄だけで賄える完全TURN数を個別に返す。後者は「生産0、外部供給0、一定需要」の限定計算であり、実際の維持可能期間予測ではない。単一スコアや高低の善悪を付与しない。

世界総量と国別分布は別取得できる。世界総量が残っていても一国が不足するfixtureを検証する。相互融通はまだ行わない。

## 保護境界

V1/V2のコード・UI・研究結果・既存JSON・Simulation Engineは変更しない。第1段階contractも変更せず拡張envelopeで使用する。既存test runnerがtests/v3を自動検出するため接続変更は不要。

「世界の法則は設計する。世界の結末は設計しない。」は厳密なschema、物理入力だけを取る純粋関数、未来役割・TURN予定fieldの拒否で維持する。初期差が後の世界に影響すること自体を否定せず、その意味を物語へ先取りしない。
