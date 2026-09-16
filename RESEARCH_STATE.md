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
