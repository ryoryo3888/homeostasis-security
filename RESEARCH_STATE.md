<!-- MACHINE STATE START -->
## 現在地（機械可読stateから生成）

一次情報: [results/status/latest.json](results/status/latest.json)。
生成時branch: `choice-id-one-turn-probe-20260917` / ソースcommit: `c434a660220b1720fe8c4c10ee836f3e587e0259`（公開コミット自身ではありません）。
最新run: `20260917T075421Z-11147417` / experiment / success / 完了8TURN / API 80 calls / retry 0。
無料検証: PASS。次: Separately authorize the next minimal experiment; never automatically advance.
今回の観測ファイル生成によるGemini API calls: 0。以下の既存文章は時点ごとの研究記録であり、現在地はこの欄を優先します。
<!-- MACHINE STATE END -->

## 8TURN run #2 故障診断（2026-09-17、最新評価）

`20260917T071205Z-fb7f949f`: 2TURN完了、29 calls、retry 0。全回答の契約はPASS。TURN3決済で直接援助とpool引出しが受取容量を二重計上しFRAGILE logistics=105となって停止。SMALLは原因Agentではない。汎用的な共有容量配分とfractional上限修正を実装。無料check 283件＋実SDK4件PASS。保存TURN1/2完全一致、TURN3決済/world/復興のcounterfactual PASS、Evaluator未取得は補完しない。失敗runはresearch対象外・原本不変。**8TURN READY: YES（修正版による新runのみ）**。別途許可後、新run_id・最大80 calls・retry 0。resumeと自動進行は禁止。今回API 0。

[診断一次情報](results/status/diagnostics/20260917T071205Z-failure-diagnosis.json) / [詳細](docs/audits/20260917T071205Z-failure-diagnosis.md)。以下は過去時点の記録。


## fresh 1TURN最終監査（2026-09-17、最新評価）

`20260917T063102Z-2d170cd8`: PASS。10/10 calls・retry 0。全Agent契約・choice復元・decision/transport監査・secret scan PASS。全8国家が同時決済に参加し、保存状態・復興73.072・Evaluator入力が無料再計算と完全一致。UnicodeEncodeError再発なし。自動公開80939faとCI 35190257103成功を確認。実行元コードと無料checkのsource digest一致。**8TURN READY: YES**。追加probeではなく、別途明示許可後の8TURN 1世界線（最大80 calls、retry 0）を推奨。1TURN自体はresearch対象外。今回のAPI callsは0、原本不変。

[機械可読監査](results/status/diagnostics/20260917T063102Z-final-audit.json)。以下は過去の評価であり、未発見・NOという記録は当時の状態。


## 最新観測・同期導線（2026-09-17）

確認できた最新保存runはprobe `20260917T022330Z-a9d78ed9`（success、1試行、retry 0、監査・契約・secret scan PASS、UnicodeEncodeErrorなし）。これはf81da80ですでに公開済み。申告された新fresh 1TURNは本checkoutの保存結果から未発見で、run_id/保存先の確認待ち。新1TURNのsettlement・world・Evaluator整合は未確認、**8TURN READY: NO**。未発見runの成功を推定しない。

実験終了後の自動sanitize/validation/status/commit/push/fetch・remote照合を実装。同期失敗時はmake sync-statusだけを再試行し、実験は再実行しない。[仕様と調査](docs/REMOTE_PUBLICATION.md)。今回の追加API callsは0。過去run不変。

## 最新設計診断・修正（2026-09-17）

[機械可読診断](results/status/diagnostics/20260917T004355Z-design-diagnosis.json) / [診断書](docs/audits/20260917T004355Z-design-diagnosis.md)。根本原因は証拠不足で未確定。SDK/HTTP設定値のencoding不適合が最有力で、合成入力により無料再現。日本語promptは成功1TURNと同一で実SDKモックでも正常。

送信前検証・接続方針・秘密を含まない失敗段階記録・null/0試行publicationを修正。make checkは265テスト＋実SDK HTTPモック4件PASS、外部API calls 0。過去run不変、失敗runはresearch対象外。**8TURN READY: NO**。次は別途許可された既存1-call probe（最大1、retry 0）だけで停止し、実認証/接続を確認後にfresh 1TURNの要否を判断。以前の状態は以下に履歴として保持。

## 最新experiment観測（2026-09-17）

`20260917T004355Z-c09ce05c`: failed、完了0TURN、transport試行1回、retry 0。TURN1・地球調整機関でUnicodeEncodeError。構造化回答は未取得で具体的なvalidation理由は保存されていない。Gemini側の受理・課金は不明。decision/transport監査・secret scanはPASS、contractsはFAIL、research対象外。今回の解析・同期API callsは0。

観測生成器がnullのmodel_responseを辞書として扱うAttributeErrorを再現。既存validatorを通した観測状態だけを公開し、原本・コードは変更していない。恒久的なexporter修正とUnicodeEncodeErrorの診断は未実施。8TURN READYはNOへ戻し、自動再実行は禁止。以前のYESは実験前ゲートの履歴として保持。

## 最新無料ゲート：8TURN READY: YES（2026-09-17）

fresh修正版1TURN `20260917T001606Z-c7bae18f` は10/10 calls・retry 0で完走。全8国家の契約・監査・同時決済・Evaluator整合・secret scan PASS。make checkは255テストと無料preflight PASS。今回のAPI callsは0、過去run改変なし。8TURNは未実行で、実行には別途明示許可が必要（1世界線・最大80 calls・retry 0）。この1TURN自体はresearch対象外。

[ゲート詳細](docs/audits/20260917T001606Z-eight-turn-gate.md) / [一次情報](results/status/development.json)。以下の旧監査は履歴として保持。

## 旧条件決済監査（2026-09-17、fresh 1TURNで再確認済み）

[機械可読な正式開発状態](results/status/development.json) / [8国家一覧・監査報告](docs/audits/20260916T233557Z-settlement.md)。対象run `20260916T233557Z-2a8367e6` の条件決済監査は **FAIL**。循環条件を除外した実装を修正し、255件の無料テストはPASS。**8TURN READY: NO**。修正版での1TURN確認は別途許可後。既存runは不変で、新たな正式研究結果はない。今回のAPI callsは0。

# HOMEOSTASIS SECURITY — 研究状態

更新: 2026-09-17。今回の作業範囲は基盤整備・無料検証のみ。Gemini API calls = **0**。キー要求・有料実験なし。

## 現在地

- 研究段階: 創発的な閉ループ研究の開発基盤と無料検証。新方式のGemini実証は未実施。
- 現在branch: `choice-id-one-turn-probe-20260917`。調査時HEAD: `f853d02`。
- main: `1eb36c8`。HEADはmainからchoice-ID/preflight/probe関連の8コミットが進んだ状態。`choice-id-preflight-20260917` と `choice-id-gemini-probe-20260917` の後続。
- 調査時、追跡済みファイルの未コミット変更なし。未追跡のPythonキャッシュと `results/final/gemini-emergent-pilot-20260917-01.json.checkpoint` あり。いずれも削除・移動なし。
- 調査時、Makefileと本ファイルなし。既存CIはUIプレビュー生成。今回、全push/PR対象の無料CIを追加。
- 最後に成功した検証: `make check` — 全214件のunit tests、choice-ID、全action contracts、invalid combinations accepted = 0、API-free 8TURN PASS。最終件数は `results/debug/check.json` の `tests` を参照。
- GitHub Actions自体は未実行（pushしていない）。同じ検証コマンドをローカルで実行済み。

## 現在の実験方式・確定仕様

国家の安全保障行動を生命体の恒常性反応として捉える。観測 → 発見 → 新しい問い → 比較実験 → 次の発見を繰り返す。

初期危機のみ固定: A国ミサイル誤着弾 → B国民間農地、年間8,000t相当の生産能力喪失。8国家モデルでの被害対応先は既存仕様のFRAGILE。TURN2以降は成立行動・世界状態・履歴からイベントを派生させる。農地復旧は被害・資源・復旧能力・紛争負荷・実際に決済された支援から計算する。

国家は互いの当該TURN回答を見ず、独立の観測・履歴に基づき判断する。Pythonが実行可能候補を生成し、AIはchoice-IDと量を選ぶ。Pythonがactionへ復元・契約検証・同時決済する。Evaluatorの文章評価で物理指標を上書きしない。

- CHECK: API上限0。ネットワーク遮断、実SDKクライアント禁止。
- PROBE: 1 Agent / 最大1 call / retry 0。
- ONE TURN: 国家8＋調整機関＋Evaluator / 最大10 calls / retry 0。
- FULL: 8TURN / 1世界線 / 最大80 calls / retry 0。
- 有料モードは通常予定表示のみ。明示実行でも最新コードの無料チェックPASSが必要。送信前の監査記録とtransport上限で停止する。
- 旧内部APIの `retry_limit` は歴史的な名称で「総試行数」。1がretry 0。旧multi-run関数は互換用に残るが、新CLIは1世界線のみ。

## 分かっていること

実行可能性とAI判断を分離して全行動契約を通せる。疑似Agentで8TURNの決済・派生イベント・状態依存復旧・監査を無料確認できる。既存無料テストの引数不足、/tmpの外部baseline依存、旧schemaテストが新シナリオを読んでいた問題を修正した。研究数値を書き換えてPASSさせていない。

## まだ分からないこと

実モデルが新choice-ID契約を安定して守るか、国家ごとの判断差・緊張・過剰/過少反応・回復・履歴依存・局所/地球恒常性がどう現れるかは未検証。無料疑似Agentの結果は実AIの創発性の証拠ではない。1runから一般化せず、関連を因果効果と呼ばない。

## 正式研究結果と保存

既存V1の16条件・36run、V2、既存JSONとDashboardを保持。既存 `results/final` のGemini audit付きpilotはすべてrejected/aborted。途中checkpointは正式結果ではない。今回新たな正式Gemini研究結果は **なし**。

新規のdebug/probe/rejected/researchを分離。research入場条件は8TURN完走、schema検証、必要ログ、API audit、研究条件PASS。全TURNで回答が収束するrunは自動採用しない。この規則は研究の採否を区別するもので、Agentへ多様な回答を強制しない。未来のDashboardは `accepted_research_paths` で正式結果だけを列挙できる。既存Dashboardは改変していない。

## 次の最小実験

無料基盤PASS → 別途明示許可したGemini 1 Agent / 1 call probe → 1TURN / 最大10 calls → 8TURN / 1世界線 / 最大80 calls。各段階で観測・失敗理由を確認し、新たな問いを記録する。今回の許可は無料検証までであり、次の有料段階は実行していない。

## 禁止事項

- 初期事故以外の出来事・行動・回復経路の脚本化。
- 新方式での固定TURN農地復旧。
- debug・probe・失敗結果のresearch混入。
- preflight失敗状態でGemini本番実行。
- いきなり大量API call、無制限retry、上限回避。
- AIに実行不能なaction tupleを自由生成させること。
- 既存研究結果の削除・無断移動・都合のよい数値変更。
- mainへのforce push等の破壊的Git操作。

## choice-ID監査の補強

追加Gemini呼び出しなしで共通監査を補強。今後のprobe・1TURN・8TURNは元の選択回答と復元actionを同一記録に保存し、transportと識別子で対応付ける。監査保存失敗は即停止・研究不採用。過去probe `20260916T213715Z-a59dc6a3` の元choice-IDは未保存のまま保持し、逆算値を書き込まない。次の最小有料段階は、別途明示許可した新しい1-call probeによる監査確認。今回有料実行なし。

## 1TURN失敗の無料診断（20260916T223649Z-60aff84a）

保存済みtransportとcheckpointによる実消費は2 calls（調整機関成功＋最初の国家ECON失敗）、retry 0。ECONはCONDITIONAL / conditions={} を返した。choice A005、資金10.0（FRAGILE向け、上限11.9）は有効。旧送信schemaのconditionsは単なるobjectで空を許したが、PythonはCONDITIONALに非空の実行条件を要求していた。理由文にある中立機関の監督は現在の環境契約で判定できず、勝手に成立扱いしない。

条件型・国ID・数値範囲をschemaへ定義し、response ID/labelとconditionsの整合をanyOfで拘束。構造化できない必須条件はREJECTと公開理由で表現する。元回答を受諾へ変換せず、choice-IDと数量の厳格検証を維持。失敗記録は改変せずrejectedに隔離。修正中API calls 0、SDK設定構築と疑似回答による無料テストのみ。新schemaの実API受理・全国家の回答は未検証で、次回の別途明示許可された1TURNで確認する。
