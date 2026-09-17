# 原則の実装接続とCodex品質評価

正式基準: [Design / Research Principles](../DESIGN_RESEARCH_PRINCIPLES.md)。評価時点は最初の完全worldline解析。今回UIを作り替えたり新実験を行ったりしていない。

## 現状評価

| 領域 | 既に成立する部分 | 不足・判断 |
|---|---|---|
| 内部構造 P1 | choice-IDと復元契約、同時条件集合、atomic決済、資源invariant、API予算・retry 0、fail-closed | gemini_agents.pyのpayload/契約/力学の密結合と長い式。小さな責務への抽出は完全replayを足場に行う。動的実行が通ったこととモデル意味論の妥当性は別 |
| 証拠 P2/P5 | durable transport、公開decision、原本hash、runtime、sanitized status、自動remote照合、失敗隔離 | 実行失敗の主体と最後のAgentを混同し得る旧failure表示。例外stageを明示する将来改善。provenanceは記録で、署名や第三者課金照合ではない |
| 現象 P2 | 実現資源、未達、条件、国別状態、世界状態、event候補を今回timeline化 | 指標の更新式・重複要求・pool滞留・条件参加と実現量の違いを直感的に説明する画面が必要 |
| 外観 P3/P4 | 複数の既存Dashboard、共通UI SYSTEMとCSS、閲覧導線 | この新worldlineへの正式bindingと視覚的検証は未実施。既存画面を閲覧しただけで芸術品質PASSとは評価しない。反復試作、実機/画面幅/操作評価が必要 |
| 研究 P5 | 初の完全8TURNを再現できる、観測/解釈/仮説を分離 | n=1。重複需要の意味、指標の較正、消費/生産/復興の結合、ID意味の偏り、独立比較と不確実性が未検証 |
| 社会実装 P6 | 原本・公開層の分離、監査、API制御という基礎 | 現実データ・妥当性検証・意思決定責任・制度適合・安全運用・人間の承認は未実装。現実の予測製品としては未成熟 |

総評: **検証可能な研究プロトタイプとして前進。科学的較正と芸術作品としての完成度はこれから。** 研究に採用されたrunと、研究装置自体が現実に妥当であることを区別する。

## 実データを視覚へ写す契約

以下は提案仕様。timelineの `turns[i]` を `T` と表記する。描画用view-modelは原本を書き換えず純粋関数で生成し、出力にrun/turn/field pathを持つ。表示上の補間には「TURN間の演出補間」を表示する。観測点は8点で、連続観測と見せない。

| visual primitive | 一次field / 変換 | 芸術表現と読み取り | 誤読防止・検証 |
|---|---|---|---|
| 条件依存の結線 | T.derived.condition_edges / dependent→required、condition_checks | 静かな8ノードの星座。選択すると依存経路だけ発光し、条件が満たされない辺・ノードを分断線で示す | trustの辺ではない。重みなし。FOOD依存20回は延べ頻度、強さではない。cyclesは実在時だけ環状強調 |
| 資源の流れ | T.executed_state.atomic_settlements.realized、requested、unmet | 資源別の光の帯。実現量を帯幅へ線形写像、要求を輪郭、未達を斜線として同時に見せる。poolを容量100の明確な貯留槽にする | 代理要求agentと物理source=world_poolを分離。国向け転送と固定networkを別レイヤー。資源を混ぜた単位不明の総流量を作らない |
| 世界状態の軌跡 | T.executed_state.true_world / research_metrics | 共通TURN軸の複数の細い軌跡。選択TURNを縦の光で結び、同時に回復とHomeostasisの乖離を見せる | 軸・単位・0〜100を固定。スムージングで極値を増やさない。シナリオ初期値と再集約値の段差を明示 |
| homeostasis pulse | global_homeostasis / 0〜100の値を固定範囲の輪郭面積に写す | 世界の周囲の静かな輪郭と、TURN移動時だけ一回の応答。数値を併置する | 心拍・生命状態を測定したと見せない。時間周波数に架空意味を持たせない。reduced-motionは静的輪郭 |
| trust / conflict field | world.international_trust / conflict_load | 2つの独立した色面・等値帯で、Trust増とConflict増の共存を表す | 位置情報がないので地理的熱分布・国境ごとの緊張を捏造しない。値と凡例、更新式へのリンクを併置 |
| 復興の断面 | reconstruction.before/after/domestic_recovery/external_support | 残存被害を切断面として表し、国内/外部寄与を異なる質感で積層。8000基準の固定面積 | 回復の内訳は式による計上で、介入の因果効果ではない。減ったdamageを増産foodの粒子へ変換しない |
| decision provenance | decisions[].call_id/model_response/choice_response/materialized_action、source_hashes | ノードから証拠の断面が開き、choice→tuple→条件→実現量へ深く入る | 公開理由だけ表示。SDK内部/内部推論/秘密は一切載せない。schema PASSと参加PASSと量の実現を分ける |
| branching worldlines | 将来の独立runと明示された親・介入metadataのみ | 同じ初期条件から比較可能な独立軌跡を束として提示 | 現在1worldlineなので枝を描かない。架空の反実仮想枝を実測として追加しない。失敗は停止点、欠損は空白 |
| event候補の舞台 | T.event_derivation.candidates / priority / excluded_recent_events | 候補を高さで示し、cooldownの覆いと実選択を見せる | 選択eventを「最大危機」と呼ばない。cooldownで順位が覆ることを操作で確認可能にする |

音を導入する場合は実在するTURN/選択/転送の到着に同期する補助表現とし、音だけの情報を作らない。色・光・音を増やすより、同じデータ構造から統一した表現を生む。

## ハッカソンまでの最小作品

1. このworldlineだけを読む新しいread-only観測画面を別入口に作る。既存Dashboardの内容を保持する。
2. 最初の一画面は「高い協調、回復する被災地、低下する全体余力」を、軌跡＋pool＋条件networkで同時に知覚できる構図にする。
3. T4を選ぶと7国家の同一支援先要求350→実現50→未達300が見え、T6 SMALLの条件不成立、T8供与側の自己引出しまで追えるようにする。
4. 一クリックで原文理由・choice・tuple・実現量・hashへ進める。デモの結論を成功物語に固定しない。
5. 数値/辺/流れとJSONの一致、欠損表示、幅違い、キーボード、色覚、reduced-motionを検証し、ユーザーが何を読み取ったかで評価する。

優先順位は新しい装飾群ではなく、**一つの本物の現象を圧倒的に美しく、根拠まで追える形にすること**。今回の成果はそのためのデータ契約と証拠で、画面完成を主張しない。

## 研究版の次段階

- まず無料で単位・在庫/flow・指標定義・event選択・条件意味を整理し、既存runを変更せずモデル仕様の曖昧さを記録する。
- H1〜H4を事前登録。成功run選択バイアス、SDK/model/source version、seedの限界、モデル非決定性、複数独立worldline、比較条件・不確実性の表示を計画する。
- 現実の法則を意味しない更新式由来のパターンと、Agent判断由来の分布を別に測定する。追加API実行は別途明示許可と予算確定後。
- 力学・契約・payload・監査・分析・描画の責務を分けるリファクタリングは、今回の8TURN完全replayを回帰基準にし、研究意味の変更と単なる構造整理を混ぜない。

## 社会実装へ進む条件

実データの出所・利用権・鮮度、実世界との較正、感度・頑健性・分布外評価、独立した専門家検証、Human-in-the-loop、説明と反証の経路、利用者と責任主体、誤用防止、停止・異議申立て、運用監視を整える。制度・安全要件は想定用途ごとに調査する。現段階はそこへ接続可能な研究基盤であって、政策判断を自動化できる完成品ではない。

## Phase 1実装

[WORLDLINE OBSERVATORY](../worldline_observatory.html) を新入口として追加した。上記の現状評価は初回解析時点の記録。現在の表示契約・実装・8領域の品質評価と残課題は [Phase 1評価](WORLDLINE_OBSERVATORY.md) を参照する。既存Dashboardと研究原本は変更していない。
