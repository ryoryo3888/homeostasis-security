# V3 横断レビューと実装仕様 — ユーザー確認版

2026-09-18 / specification revision 1（初回レビュー履歴）。

**更新：主質問③・副質問①②と第1段階が承認済み。** 最新契約は [PHASE1_CONTRACT.md](PHASE1_CONTRACT.md)。以下の選択待ち・未承認は初回レビュー時点の記述。

本書は4文書を再読したレビュー結果であり、V3の共通実装契約を確定するためのレビュー版。相違があれば本書を優先する。研究質問、実験パラメータ、実装着手を承認済みとは扱わない。コード・schema・UI・Registry・研究原本には変更を加えない。

**作品には自由。研究結果には厳格。** 規模、資源数、観測層、worldline数、V4以降を審査都合で制限しない。拡張は「観測→問い→必要な機構→検証→新しい観測」の系譜を記録する。8国家はV3の基準構成であってengineの固定上限ではない。

## 1. 4文書の横断レビュー

対象：[README](README.md)、[資産調査](ASSET_SURVEY.md)、[世界モデル](WORLD_MODEL.md)、[体験・段階計画](EXPERIENCE_AND_PLAN.md)。既存コードの出典は資産調査のM/R commitを固定して使用する。

| ID | 発見した問題 | 解消した仕様／判断 |
| --- | --- | --- |
| R01 | A分類の契約継承とコード無変更継承が混在 | 契約・保護文書はA。資源型に依存するchoice/auditコードはB。ファイル全体をAとしない |
| R02 | ObservatoryがBとCに重複 | view-model実装はB、保存済み世界線と完成展示はC。旧表示をV3として公開しない |
| R03 | failed fixtureをDとしながら回帰試験で利用 | DはV3世界の初期状態・研究結果に継承しない意味。故障検出教材としての参照は許す |
| R04 | 「各1契約束」「少数指標」「最初は最小」が恒久制限に見える | 参照試験構成と研究上の採否を区別。件数はprotocol設定、solverは置換可能、結果意味は固定 |
| R05 | 資源の単位・能力・再生・復興消費が未確定 | §5の型・整数量・収支台帳・出力可用時点を採用。旧値の自動換算を禁止 |
| R06 | 多段依存と同TURNでの再利用の関係が曖昧 | §5で遅延付き辺、投入依存、次TURN出力を定義。現行6辺では多段伝播検証を満たさない |
| R07 | 比例配分／max-min「等」、集合間選択が未定義 | §6の有限離散問題・leximin・安定tie-breakを基準制度として確定。制度効果も研究対象 |
| R08 | 取引のatomic性が遅延着荷まで保証するように読める | 発送時の全脚同時所有権移転と、後の配送を分離。輸送中損失は明示的な別イベント |
| R09 | 参加条件と実現量条件を同一固定点で扱い得る | 単調参加だけ旧固定点を利用。数量条件は全体制約で判定し、実現量から再検証 |
| R10 | REJECTと独立行動、相手の受領同意が未確定 | proposal responseとintentを分離。REJECTでも自己権限内行動可。相手資産を使うには同意必須 |
| R11 | 国家判断を提案前に置く例と実コードが異なる | 現行同様、提案前に追加AI判断callを挿入しない。独立観測→提案→独立回答を正式順序にする |
| R12 | Evaluator前に復興が完了していない | 評価は復興・消費を含む正式TURN末候補snapshotの後。hash一致を必須にする |
| R13 | 主質問未選定なのに正式指標・実験条件が決定済みに見える | 共通記録軸を確定し、primary endpoint・方向仮説・反復数は選択後の事前登録と分離 |
| R14 | 成功と回復、収束と無効が混在し得る | completion/validity/outcome/publicationを独立管理。全拒否・非回復を技術不正にしない |
| R15 | 指標・TURN・公開境界が複数文書で重複 | 本書を規範、他4文書を背景・出典・視覚意図とする。規範値を複数箇所で管理しない |

削除する研究資産はない。延期する機構には研究理由を付ける：内生価格市場は現候補が物量・権限・経路で検証可能なため必須ではない。医療資源は現在の一次観測に固有の需要・供給証拠がない。多ラウンド交渉は交渉過程そのものの効果を問う場合に導入する。現実地理は距離・地理障害の仮説を検証するときに追加する。いずれも規模を理由とする永久禁止ではない。

## 2. 研究質問候補（原文を保持・順位なし）

### 1. 独立した国家の条件付き協力は、有限資源の不足をどこまで吸収できるか？

- 観測：参加意思、条件、実現援助、不足の残存、負担配分。
- 連続性：V1の二国間応答→V2の非強制提案→V3の多数主体による条件付き配分。
- 有限資源：約束と実現量の乖離、共有容量競合を生じさせるため必要。
- 8国家：供給者・需要者・仲介者・脆弱国を同時に含み、二者交換に還元できない競合・循環を比較する基準。8が数学的最小数という主張はしない。
- ネットワーク：資源が存在しても届かない状況、代替・依存条件を検証するため必要。
- 検証仮説例：固定した需要・総量・外乱で、指定した条件付き制度が参照制度より累積不足を減らす。
- 反証／未支持：事前登録した差の方向と逆で、反復の不確実性区間も反対側なら当該条件内で反証。差の区間が0を含む／実質差の閾値を越えなければ未支持。資源の増量で生じた差を制度効果としない。

### 2. 資源依存の構造は、局所障害の波及と回復経路をどう変えるか？

- 観測：不足の到達国・到達TURN・経路、代替経路負荷、回復時間。
- 連続性：V1の局所危機→V2の地球指標への影響→V3の伝播経路を分解した説明。
- 有限資源：代替供給・備蓄の吸収限界を作る。無限供給ならボトルネック仮説を検証できない。
- 8国家：複数の段階・供給源・需要先・迂回路を併存させる基準。国家数自体の効果は別比較にする。
- ネットワーク：この問いの操作変数そのもの。投入依存と運搬辺を分ける。
- 検証仮説例：総量・容量・外乱条件を対応させた分散依存構造が、集中構造より到達範囲または累積不足を減らす。
- 反証／未支持：方向が逆ならその条件下の仮説を反証し得る。差なしは未支持。迂回路の総容量まで増えた比較は構造単独の検証として不十分。全条件で分散が優れるとは主張しない。

### 3. 世界の安定化は、国家の自律性や資源分布とどのように両立・衝突するか？

- 観測：世界変動・機能充足と、国別負担・選択・資源分布の同時軌跡。
- 連続性：V1の平衡→V2の主権と全体回復→V3の安定と分配・自律性の非同一性。
- 有限資源：配分と留保の実質的trade-offに必要。拒否数だけの観測にはしない。
- 8国家：同じ集計値でも複数の受益・負担分布を持ち得る異質な母集団として使用。
- ネットワーク：形式的に選択自由でも依存によって実行可能選択肢が狭まる機構を観測する。
- 検証仮説例：指定制度で変動が減っても、国別最低充足率または留保条件の達成は改善しない場合がある。
- 反証／未支持：普遍的な衝突を主張するなら、定義した自律性を保ち分配も改善する事例は反例。限定条件の仮説は事前指定endpointの差で評価。衝突を一例で一般化せず、見つからなかったことを不可能の証明にしない。

問い自体は開かれた問いであり直接の真偽命題ではない。ユーザーが問いを選んだ後に、方向、最小実質差、観測期間、反復数、不確実性推定法、多重比較の扱いを登録する。ここで数値閾値や研究結果を捏造しない。seed対応はAI出力の同一性保証ではない。

## 3. 旧資産の最終分類

M/R revisionはASSET_SURVEY.md記載値。省略したcore名は `homeostasis_core/` 配下。Aは表に示す対象範囲そのものを継承する。テスト未実施で「V3適合済み」とは言わない。

| 対象ファイル／範囲 | 現在の役割 | 分類 | 理由・V3での扱い |
| --- | --- | --- | --- |
| M `docs/architecture/HOMEOSTASIS_VISUAL_CONSTITUTION.md`, `LAYOUT_CONTRACT.md`, `CONTENT_SLOT_CONTRACT.md` | 完成画面保護 | A | V1/V2の規則を無変更維持。V3専用契約を追加する |
| M `ui/layout-guard.js`, `ui/content-slots.js`, `tests/layout/` | runtime移動防止・slot・回帰 | A | V1/V2用資産としてそのまま保持。v3を黙って対応追加しない |
| R `DESIGN_RESEARCH_PRINCIPLES.md` | 科学・芸術・証拠原則 | A | 原則を継承し「作品には自由。研究結果には厳格」を本仕様で明文化 |
| R `action_choices.py`, `decision_audit.py` | catalogue復元・回答trace | B | 原則は継承、単位・複数契約・snapshot参照への型修正が必要 |
| R `api_budget.py`, `transport_safety.py` | 呼出し上限・SDK境界・秘密分離 | B | V3 runnerとの接続・protocol由来予算を再検証。retry 0方針はそのまま |
| R `models.py`, `config/country_archetypes.json` | 8国家・指標・資源型 | B | 属性を継承、stock/capacity/demand/権限を分離。旧初期値は自動換算しない |
| R `resources.py`, `scenarios/resource_network_sample.json` | 6辺供給・消費 | B | 有向辺を出発点に、多段依存・遅延・共有予約を導入 |
| R `feasibility.py` | 個別可否・atomic配分 | B | 集約制約、実現量条件、多脚、受取権限へ拡張 |
| R `gemini_agents.py` | proposal/国家/評価、条件、world更新 | B | parserとcoreを分離し、REJECTと独立intentを分離 |
| R `final_experiment_runner.py`, `emergent_dynamics.py`, `metrics.py` | TURN・復興・集計 | B | 正式末状態、収支、定義version、派生イベントを整合 |
| R `research_validation.py`, `observability.py` | 研究gate・sanitized観測 | B | 固定80call/8TURNからprotocol検証へ。結果の良否と技術資格を分離 |
| M `research/experiments/registry.schema.json`, `registry.json`, `artifact_allowlist.json`; `tools/experiment_registry.py` | V1/V2の登録と参照検証 | B | 将来v3対応を明示migration。現在のrecordは変更せず旧検証継続 |
| R `worldline_observatory.html`, `tools/analyze_worldline.py` の実装 | 観測UI・純粋変換 | B | 原則と変換責務を再利用、単一run依存を分離 |
| R `tests/final/test_phase9_atomic_settlement.py`, `test_mixed_settlement.py`, `test_simultaneous_conditions.py` | 旧契約の回帰試験 | B | 旧試験は保持。新意味論向けassertion/fixtureを別追加。無変更でV3試験としない |
| M `dashboard_v1.html`, `dashboard_v2.html`, `v2_first_run.json`, `summary.json`, 既存36系列 | 完成作品・先行研究 | C | 保護・参照のみ。V3行動や結果の正解として流用しない |
| R `results/status/runs/20260917T075421Z-11147417/`, `docs/research/20260917T075421Z-11147417-*.md`, `results/status/analyses/20260917T075421Z-11147417/` | 正式8TURNと解釈 | C | 原runの資格と由来を維持。V3へ再ラベルしない |
| R `docs/audits/`, `results/status/diagnostics/` | 故障と修正の履歴 | C | 設計の根拠、誤りを隠さず参照 |
| R `results/status/runs/20260917T004355Z-c09ce05c/`, `20260917T071205Z-fb7f949f/`、probe/単TURN各run | 故障・境界確認 | D | V3正式母集団へ継承しない。失敗資料は削除しない |
| R `tests/fixtures/settlement_20260916T233557Z.json`, `settlement_20260917T071205Z.json` | 旧故障再現入力 | D | V3世界入力にはしない。旧回帰・移行差の教材として保持 |
| M `results/final/deterministic_prototype*.json`, `gemini-run-*.audit.json` のrejected/aborted系列 | 合成・旧仕様・失敗 | D | 昇格・結果補完・削除をしない |

## 4. 必須構造と現在地

「必須／将来」はV3への必要性、「既存／修正／新規」は実装状態という別軸。

| 構造 | 採否 | 現在地とV3仕様 |
| --- | --- | --- |
| 8国家、独立判断、非強制Coordinator | 必須 | 既存。属性・観測契約を修正。国家数は設定駆動 |
| 有限資源、国別保有、国別需要 | 必須 | 既存部分あり。全国家の明示需要と収支へ修正 |
| 資源network、供給制約 | 必須 | 既存。共有容量・権限・経路を修正 |
| 複数段依存 | 必須 | 新規。連鎖と迂回・備蓄による吸収を検証可能にする |
| 提案／意図／feasibility／実行の分離 | 必須 | choice方式は既存。複数当事者の集約判定を修正 |
| 原子的取引、保存則、成立分のみ反映 | 必須 | 既存部分あり。消費・生成・損失・輸送中まで拡張 |
| 閉ループイベント | 必須 | 既存。複数圧力と二重適用防止・由来を修正 |
| 複数worldline・比較 | 必須 | 旧run識別は既存。protocol/hashによる比較適格性を追加 |
| 非回復世界と技術失敗の保存 | 必須 | 保存基盤は既存。outcomeとvalidityを分離 |
| 評価役、監査、Registry接続 | 必須 | 既存。評価時点・schema migrationが必要 |
| Earth中心のread-only観測、拡張slot | 必須 | 既存原則を継承。V3独立入口は新規 |
| 資源追加、国家数変更、network追加、V4 | 将来拡張可能 | version化と問い／単位／保存則／出典を伴い追加。恒久上限なし |
| 内生市場、現実地理、多ラウンド交渉、医療 | 現候補では将来 | §1の研究理由。必要な問いが生まれたら再審査 |

## 5. 4設計課題の解決仕様

### 5.1 資源と能力

**問題**：stock、能力、評価値を0〜100で共用し、物流・発電能力を物品のように移転できる。消費不足が入荷不足と混ざり、復興に使った資源の引落しがない。

**確定仕様**：

- `Stock(resource_id, owner, location, amount, storage_limit, unit_id)`、`Capacity(service_id, owner, available_per_turn, unit_id)`、`Indicator(definition_id, value)`を異なる型とする。
- 数量はresourceごとの最小量子を単位とした非負整数。量子はprotocolで必須、実物への換算根拠がなければモデル単位。capacity換算・recipe係数は有理数、必要投入は切上げ、出力は切下げ、端数は記録する。旧floatを黙って丸めない。
- food/fossil/fundsは別stock。renewable/nuclearは発電capacity、logisticsはサービスcapacity。gridの送電capacity・storage容量・resilience指標を別fieldへ。電力出力は既存energy概念を明示したTURN内energy勘定であり、発電capacityを売買するものではない。
- 全国家に需要表を必須化。未定義は0ではなくscenario validation失敗。明示0は合法。food等の需要と投入用需要を分離する。
- 基準制度は明示した必要需要を先に予約し、残りを取引・生産・復興に割当てる。需要放棄を扱う将来制度は別policy ID。処理順による暗黙優先を禁止。
- 生産・発電・復興はrecipe ID、入力、capacity、出力、損失を台帳に記録。recipeなしに資源は再生しない。発電の外部energy源も明記し、未モデル化した燃料を無限実物燃料と主張しない。
- 移転総量は厳密保存。資源別に `期末=期首+明示source−実消費−損失−外部sink`。復興は消費済み入力からdamageを減らし、翌TURN利用可能capacityへ反映。同じ援助量を消費・輸出・復興で重複使用しない。

**解決判定**：型混同拒否、全国家需要検証、消費と備蓄による充足一致、全台帳の整数収支ゼロ、復興費用引落し、capacity超過拒否。これらの無料試験が通ること。

### 5.2 多段階依存

**問題**：現行6辺は一段供給。入力不足が出力・別国の不足へ伝わる規則がない。

**確定仕様**：供給辺と投入recipeを別graphにする。edgeには端点・resource・容量単位・遅延・使用権・稼働率、recipeには投入係数・出力・稼働上限・遅延を必須化。基準は物品1辺につき1TURN以上、出力は次TURNから可用。同TURNで新入荷を再輸出しない。期首到着分は開始snapshotの在庫として利用可能。発送時に受取保管容量も予約し、到着時に予約をstockへ振り替える。予約中に容量を失う外乱は不足分を明示した損失／代替保管ledgerとして処理し、無言で切り捨てない。energy/serviceは同TURNのcapacity予約と消費が一致する非保管勘定として処理し、その成果は次TURNへ反映する。

輸送中は所有国と保管場所を別記録。途中損失はsource eventとsinkを記録する。現在のTURNで生じた不足から派生したeventは次TURNに一度だけ適用し、元の不足を二重に引き落とさない。複数圧力は保持し、代表タイトルだけで隠さない。

**解決判定**：少なくとも三つの有向依存辺を持つ合成連鎖で、末端障害の伝播時点・経路が規則通り一致すること。備蓄・代替を変えた対照fixtureで吸収経路も検証する。閉路で資源が増殖しないこと。これは無料テスト設計であり今回実行しない。

### 5.3 実現条件

**問題**：現行minimum_aid_amountは自己選択量、mutual_performanceは参加者数。実現援助の保証ではない。

**確定仕様**：条件を `participation`、`minimum_settled_quantity`、`minimum_arrived_quantity`、`own_burden_ceiling`、`deadline`へ型分離。受取国/resource/契約ID/判定TURN/数量を必須にする。到着条件は実際の到着台帳だけで満たす。将来到着予定を到着済みと扱わない。現在の判断に未来到着を条件とする契約はpendingとして拘束を明示し、未達時の解約規則を含む別protocolがない限りcatalogueに出さない。

参加者全体から§6の共同制約を解き、確定量で条件を再検証する。拒否・不成立は貸借ゼロ。条件不成立とschema違反を区別し、前者は世界の結果、後者は技術停止。各国の公開reasonを条件コードとして解釈しない。

**解決判定**：参加しても数量不足なら不成立、循環同意が実行可能なら成立、混合受取・pool・経路競合が保存則を破らない、入力順を変えても同じ解。不成立理由は判定根拠と制約IDを保存。

### 5.4 評価時点

**問題**：RではEvaluator呼出し後にreconstruction_stepを適用する。決済後ではあるが復興後評価ではない。

**確定仕様**：消費・生産・復興・指標・台帳検証を終えた `end_state_hash` を評価入力へ渡す。Evaluatorはコメントと自己評価を返せるが公式指標を変更できない。公式値とEvaluator自己評価を別namespaceに保存する。

**解決判定**：Evaluator入力hash、保存TURN末hash、翌TURN入力の参照hashが一致（翌TURN外乱差分は別ledger）。評価出力でworldが変わらない。評価失敗ならcomputed stateは診断保存し、TURN completedにはしない。

## 6. 意図→現実：決済契約

1. Coordinator proposalは勧告。Agent responseは賛否。intentは別のPython所有catalogueを選ぶ。REJECTでも許可された自国行動を選べる。proposal拒否だけを理由に独立行動を消さない。
2. catalogueは開始snapshot・schema・条件template・権限・経路・単位のhashで固定する。モデルはchoice ID、許可量、型付き条件、公開reasonのみ出力。自由tupleは不可。
3. 受取同意は開始時の明示standing mandateまたは共同契約署名で証明する。任意の他国支出を一国の回答で成立させない。共同契約IDは全員共通の事前提示templateから定義し、回答到着順でIDを作らない。
4. poolは任意預託、委任済み規則で払い出す。基準制度は開始pool残高のみ利用、同TURN拠出は次TURN利用、self-withdrawal可、受取同意必須。寄付は返還請求権を生まない。別制度はpolicy IDを変え比較する。
5. 各契約kについて不成立 `z=0,q=0`、全量履行 `z=1,q=requested`、部分可 `z=1,min≤q≤requested`。移転を伴う成立量の最小値は1量子。交換の全脚は同じ契約倍率に従い、丸め後も全脚・収支を検証。外交等の非物量行動は別のbinary選択として扱う。
6. 個別検証後、全候補・同意済み継続契約を同じ在庫、受入、pool、共有capacity、必要需要予約に対する制約問題へ入れる。start stock以上の送出禁止。同TURN受取・pool拠出・生産出力による再融資は禁止。
7. **基準配分規則**：全候補を含む充足率 `q/requested`（不成立は0）の昇順vectorを辞書式最大化するleximin。非物量行動・同一vectorの解は、seedと安定契約IDのdigest順に並べた成立vector、数量vectorの順で辞書式最大化して一意化する。文字列/入力順やsolver発見順を優先順位にしない。hash衝突時は安定IDで解決。継続契約も暗黙優先しない。既確定予約だけはhard constraint。
8. これは公開された配分制度であり、善い世界を中央が最適化するものではない。契約分割で配分率を操作し得るため基準protocolは各国1つの配分単位に集約し、複数脚をその中で明示する。将来複数独立契約へ拡張する際は分割耐性を別検証する。国数・世界線数の恒久上限ではない。
9. 参照実装は有限の候補・整数量による完全探索可能なfixtureで解を定義する。本番solverは同じ最適解とtie-breakを保証する実装を採用する。探索限界/timeoutは技術失敗であり無取引としない。近似解を黙って採用しない。
10. 全脚の新状態を私有copyで計算・検証し、一括commitする。遅延配送では同時に受取所有のin-transitへ貸記し、発送国から減算。着荷前の所有と可用在庫を区別する。配送事故は後続の損失イベントであり、atomic配送保証を偽らない。

記録層：`raw final response → materialized intent → individual feasibility → allocation/conditions → committed ledger → end state`。全層をrun/turn/agent/attempt/choice/catalogue/transaction IDで結ぶ。不成立理由は必ず証拠付き。共同制約で一意の原因を割り当てられない場合は複数の競合制約と「配分規則による非選択」を保存し、単一の国家責任へ変換しない。

## 7. 正式TURN順序

1. **期首**：前TURN checkpoint検証→予定着荷→事前登録外乱と前TURN由来eventの適用。順序はevent type/IDで固定し全差分記録。
2. **観測**：開始snapshotをfreeze。各国家の可視範囲・鮮度・履歴・自己資源を確定。秘密の他国回答は共有しない。
3. **提案**：Coordinatorは公開状態だけから提案。独立判断の前処理は国別観測・留保契約の準備であり、新たなAI callではない。
4. **独立判断・応答**：各国が同じsnapshotと提案から賛否・intent・条件を回答。回答順で世界を更新しない。
5. **境界検証**：strict schema→choice復元→個別在庫/経路/権限/上限の検証。一つでも不正なら停止。
6. **共同成立判定**：同意・参加・実現量条件・共有制約を同時に解き、不成立と理由を確定。
7. **作業状態更新**：成立分だけ貸借・輸送予約。必要消費→残余の生産/復興。全用途は同一台帳、出力は規定の可用時点へ。
8. **正式末状態候補**：保存則・capacity・条件を再検証し、世界指標とend_state_hashを確定。
9. **評価**：Evaluatorへ末状態候補を渡す。評価は世界にフィードバックする操作権を持たない。
10. **次TURNイベント生成**：末状態・成立行動・履歴から候補と根拠を生成し、次TURN適用queueへ。新しい外生ショックはprotocolにない限り追加しない。
11. **耐久保存**：state/ledger/回答/評価/event queue/監査のmanifestを検証してcheckpoint commit。途中障害は未完了TURNとして隔離。

保存方式は同じfilesystem内のtemp generation→全file flush/fsync→manifest検証→atomic renameによるcommit marker。中断時は有効markerのないgenerationを正式状態として読まない。復旧時にAPIを自動再呼出ししない。

## 8. 正式観測指標候補

正式採用は共通観測schemaへの採用であり、主質問のprimary endpointはユーザー選択後に定める。

| 指標 | 分類 | 計算・入力 | 分からないこと |
| --- | --- | --- | --- |
| 恒常性 | 正式 | 必須機能ごとの充足率軌跡と事前登録参照帯からの逸脱。単一合成点にしない | 理想世界・倫理的優劣 |
| 回復力 | 正式 | 機能別回復時間、累積不足、被害減少。基準帯と必要連続TURN数はprotocol必須 | 観測期間外の回復。未回復は右打切り |
| 国家自律性 | 正式 | 所有権/同意違反件数=0をinvariant化、賛否・留保充足・利用可能選択を記録 | 心理的自由、現実の主権。拒否率だけでは測れない |
| 資源不足 | 正式 | U=max(0,D−C)、C/D、累積Uを国/resource別。D=0はN/A | 入荷不足と同一ではない。異種単位合算不可 |
| 資源偏在 | 正式 | 同資源残高shareと国別充足率分布。総量0はshare N/A | 人口等を含まない公平性の断定 |
| 供給網健全性 | 正式 | 有効な需要先への到達可能性、停止辺、実配送/計画配送 | 辺があるだけで供給充足は保証しない |
| 依存集中 | 正式 | 国/resource別供給share二乗和、計画と実現を分離 | 入荷0はN/A。集中だけで脆弱性を断定不可 |
| ネットワーク負荷 | 正式 | 使用capacity/利用可能capacity、予約量、bottleneck | capacity0は停止。単一平均では局所詰まり不明 |
| 取引成立 | 正式 | 成立/有効提出、全量/部分/不成立、requested/settled/arrivedを分離 | 0提出はN/A。高成立率が良い結果とは限らない |
| 紛争負荷 | 正式 | version化した状態指標と増減の根拠項 | 実世界の紛争確率・死傷者数ではない |
| 波及 | 正式 | 初期被害国外の不足発生時刻と依存path・差分ledger | 対照なしの因果効果量 |
| 安定性 | 補助 | 同じ定義・同じ時間窓で指標の変動幅/分散 | 静止した欠乏状態も安定し得る |
| 既存Homeostasis合成式 | 補助 | 旧式と係数をlegacy定義として併記。V3対応入力が揃う場合のみ計算 | 単位・定義変更後の直接version比較 |
| trust / 自己burden | 補助 | モデル内指標／自己申告を別namespaceで表示 | 実測信頼や客観的負担ではない |
| 過剰反応・過少反応 | 今回は見送り | 参照policy・必要量・許容損失が未定義。選択した問いが要求すれば登録して採用 | 必要量を定義せずに行動を過剰/不足と評価できない |

紛争・trust等の状態更新は、規則ID、入力field、係数、clamp範囲を持つversion化transition tableで定義する。旧係数はlegacy profileとしてのみ参照し、単位を変えた値へそのまま乗算しない。具体係数・需要量・初期stock・閾値は実験scenarioの必須入力であり、隠れたdefaultなし。未設定scenarioは実行不可。この区別によりengine仕様は確定しつつ研究条件はユーザー選択後に固定できる。

## 9. 地球を中心とした拡張可能な作品

上部固定frame：**Identity → 世界状態＋操作 → Earth＋8国家＋資源・依存ネットワーク**。説明文を前置して地球を押し下げない。国配置は抽象topology、実地理の主張はしない。国数拡張時は集約・展開を用い、旧versionのEarthを変形しない。

下部slot：国家・取引詳細／TURN観測／worldline比較／研究結果／証拠。線の太さは同一単位の実量、条件線は別線種、未実現は実流と区別。state・choice・条件・ledger・原本fieldへ掘り下げる。閲覧速度・属性による指示は禁止。keyboard、reduced-motion、数値アクセスを維持。

拡張は `question_id → protocol_id → worldline_id → observation definition → approved content slot` で接続する。新資源には単位・保存式・recipe・監査を、新指標には式・適用範囲・欠損規則を必須にする。schemaはversion化し未知typeは拒否する。これは追加禁止ではなく、追加を検証可能にする仕組み。

比較はprotocol/モデル/初期条件/単位/制度の差を明示する。比較不適格な世界線も個別観測できるが、同じ統計母集団にしない。非回復・全拒否も有効なら正式記録。transport/schema/台帳故障は診断資料として保存する。

V1/V2の共有JS/CSS/DOMをV3用に変更しない。新しいversion navigationをV1/V2へ追加することも別の承認済みUI変更として影響を事前提示する。共通ライブラリ変更が必要なら両versionのsource/parent/order/bounds/interaction/copyの差分を先に示し、承認と回帰PASSなしでは公開しない。

## 10. 実装段階（全て未着手）

以下は候補ファイル名であり今回作成しない。全段階でV1/V2、旧run、旧Registry record、Baselineは変更禁止。段階化は故障点を局在化するためであり、作品の成長上限ではない。

| 段階・目的 | 変更ファイル候補 | 利用資産・追加内容 | 完了条件・検証 |
| --- | --- | --- | --- |
| 1 契約とversion境界 | `homeostasis_v3/contracts.py`, `schemas/v3/`, `tests/v3/test_contracts.py` | 旧型の教訓。stock/capacity/intent/transaction/protocol/metadataを追加 | 型混同・未知field・未定義単位拒否、旧データhash不変 |
| 2 8国家・収支 | `homeostasis_v3/state.py`, `ledger.py`, `scenarios/v3/`, `tests/v3/test_ledger.py` | archetypeの意味を継承、明示需要・権限・source/sink・復興消費 | 非負・整数保存・所有権、消費/復興二重使用拒否、0/最大境界 |
| 3 多段依存 | `homeostasis_v3/network.py`, `production.py`, `tests/v3/test_cascades.py` | 旧SupplyLink責務、遅延/recipe/共有容量/輸送中を追加 | 連鎖・遮断・迂回・備蓄・循環の無料fixture、順序独立 |
| 4 選択と原子決済 | `homeostasis_v3/choices.py`, `settlement.py`, `tests/v3/test_settlement.py` | choice-IDと旧故障教材、条件型・同意・leximin参照解 | 個別合法/共同不可能、最低量、全脚rollback、混合容量、入力全順序、solver一致 |
| 5 TURN・Agent境界 | `homeostasis_v3/runner.py`, `agent_adapter.py`, `audit.py`, `tests/v3/test_turn.py` | budget/transport方針、正式末hash、durable commit | mock回答replay、評価入力一致、fault injection、API禁止モード、重複dispatch防止 |
| 6 指標・研究接続 | `homeostasis_v3/observations.py`, `validation.py`, 将来Registry migration | 既存監査・allowlist原則。定義IDと複数worldline比較 | 未回復の受理、技術不正の拒否、比較適格性、secret scan、登録≠公開 |
| 7 V3観測体験 | `dashboard_v3.html`（将来候補）、`ui/v3/view-model.js`、V3専用layout tests | Observatoryの責務、独立frame/slotとprovenance | 研究値への逆参照、desktop/iPad、accessibility、V1/V2差分0 |
| 8 実験protocol検証 | V3 protocol文書、offline boundary tests | 質問に対応する条件・反復・予算・停止規則 | 自由回答を捏造せず無料SDK境界確認。実験は別承認後のみ |

第4段階で参照解に一致しないsolverは第5段階へ接続しない。第5段階以前に有料APIで不足実装を探索しない。UIは検証済み保存データだけを読む。V3 UIにまだ実runがなければ研究結果として合成データを表示しない。

## 11. レビュー完了と停止境界

共通実装契約は本書で具体化した。ユーザーが研究質問と設計を確認するまでは実装開始不可。残る選択は主質問と、それに対応する実験protocolの値・比較制度・endpointであり、曖昧な資源型やTURN順序を実装者判断へ丸投げしない。

今回：文書のみ。API calls 0、simulation 0、研究結果生成0。旧資産の削除0、V1/V2変更0。build/make checkを実行したという主張はしない。文書整合・参照・secret scanを確認する。
