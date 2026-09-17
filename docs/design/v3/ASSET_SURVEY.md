# 資産調査と継承境界

> 2026-09-18レビュー更新：本書は初回設計の背景・出典資料として保持する。分類・配分規則・正式TURN・指標・実装段階の確定仕様は [IMPLEMENTATION_SPEC.md](IMPLEMENTATION_SPEC.md) を優先する。実装はユーザー確認待ち。

調査日：2026-09-18。ファイルとgit treeを読んだ調査であり、新しい実験・replayは実行していない。以下のPASSは保存済み監査値であり、今回再実行した検証ではない。

## 出典を固定する

| 系譜／remote ref | 調査revision | 意味 |
| --- | --- | --- |
| origin/main | `bd41503737f6b66da892b67bf1c375077be10af1` | 現在の公開保護契約・Registryを含む設計base |
| origin/homeostasis-final-closed-loop-20260915 | `7ab2349617c398841cc3dc0e70ca42e26fc1f8e9` | 旧完全版、feasibility／atomic資産 |
| origin/research-integration-20260916 | `36e0aaad977c79897f1b5b9e79d4bd15e9226528` | 研究統合の履歴 |
| origin/emergent-worldlines-20260917 | `1eb36c8657df0273a2a9bb529994dc3a85cb169b` | 状態由来イベント・worldline分析の履歴 |
| origin/choice-id-one-turn-probe-20260917 | `ed70ee235c4ce098709c0825d055e4b64f901db8` | 修正済みchoice／settlement／監査と完全8TURNの保存資産 |

以下で **M** はmain revision、**R** は最後の研究revisionを指す。全remote refの一覧から関連系譜を抽出し、上記treeを比較した。全歴史commitを網羅的に検証したという意味ではない。mainだけを探索して「8TURN結果が存在しない」とは判断しない。

- [M：Registry](https://github.com/ryoryo3888/homeostasis-security/blob/bd41503737f6b66da892b67bf1c375077be10af1/research/experiments/registry.json)
- [R：Design / Research Principles](https://github.com/ryoryo3888/homeostasis-security/blob/ed70ee235c4ce098709c0825d055e4b64f901db8/DESIGN_RESEARCH_PRINCIPLES.md)
- [R：Creative Research Roadmap](https://github.com/ryoryo3888/homeostasis-security/blob/ed70ee235c4ce098709c0825d055e4b64f901db8/docs/CREATIVE_RESEARCH_ROADMAP.md)
- [R：国家判断・条件決済・世界更新](https://github.com/ryoryo3888/homeostasis-security/blob/ed70ee235c4ce098709c0825d055e4b64f901db8/homeostasis_core/gemini_agents.py)
- [R：実行可能性・原子的配分](https://github.com/ryoryo3888/homeostasis-security/blob/ed70ee235c4ce098709c0825d055e4b64f901db8/homeostasis_core/feasibility.py)
- [R：供給網](https://github.com/ryoryo3888/homeostasis-security/blob/ed70ee235c4ce098709c0825d055e4b64f901db8/homeostasis_core/resources.py)
- [R：実TURN runner](https://github.com/ryoryo3888/homeostasis-security/blob/ed70ee235c4ce098709c0825d055e4b64f901db8/final_experiment_runner.py)

## A / B / C / D 分類

Aは契約・責務をそのまま継承可能という意味であり、V3で無試験流用する許可ではない。BはV3仕様との差を修正して再検証する。C/Dの原本を削除・変換しない。

| 分類 | revision：資産 | 判断とV3での扱い |
| --- | --- | --- |
| A | M：`docs/architecture/` Visual／Layout／Content契約、`tests/layout/` | V1/V2を固定する規則、移動検出、viewport検証を維持。V3専用契約は別途追加承認 |
| A | R：`action_choices.py` のPython所有tuple、`decision_audit.py` のtrace契約 | モデルはIDと許可量を選択。公開理由だけ保存し、run/turn/agent/attemptで監査対応 |
| A | R：`api_budget.py`, `transport_safety.py` の予算・pre-dispatch・retry 0方針 | 秘密分離、SDK境界、失敗即停止を維持。新runnerへの接続は再検証 |
| B | R：`models.py`, `config/country_archetypes.json` | 8主体と初期異質性は出発点。単位、需要、関係、保有権を明示 |
| B | R：`resources.py`, `scenarios/resource_network_sample.json` | 有向供給・比例制約を継承。stock/capacity分離、投入依存、同意と全体ledgerが必要 |
| B | R：`feasibility.py` | 個別上限＋集約上限の二段検証を維持。複数契約、共有経路、受取同意へ拡張 |
| B | R：`gemini_agents.py` 条件・世界更新 | 同時参加集合と原子更新を維持。実現量条件、効果と選択数の区別、責務の分離が必要 |
| B | R：`final_experiment_runner.py`, `emergent_dynamics.py` | 記録・履歴・派生イベントを継承。復興とEvaluatorの順序、消費ledger、複数圧力を設計 |
| B | R：`research_validation.py`, `observability.py`、publication | 完了・監査・secret gateを維持。8TURN/80calls特化、収束による審査、stage attributionを再設計 |
| B | M：Registry schema／allowlist | 分離・hash固定・承認原則を継承。現在v3は禁止。将来明示的schema migrationのみ |
| B | R：`worldline_observatory.html`, `tools/analyze_worldline.py` | read-only view-modelと証拠参照を継承。固定runの表示をV3へ単純コピーしない |
| A | R：`tests/final/test_phase9_atomic_settlement.py`, `test_mixed_settlement.py`, `test_simultaneous_conditions.py` の不変条件 | 保存、順序独立、混合受取容量、条件循環という回帰観点を継承。fixtureは旧契約のまま |
| C | M：V1の36系列、`v2_first_run.json`、公開Dashboard | 先行研究・完成作品。V3の入力や学習用正解行動にしない |
| C | R：完全8TURN、分析／timeline、既存Observatory | 先行世界線。V3結果へ再ラベルしない、一般法則としない |
| C | R：`docs/audits/`、`results/status/diagnostics/` | 条件決済、Unicode、混合容量故障の設計履歴。検証教訓を保持 |
| D | R：probe／単TURN／failed run、`tests/fixtures/settlement_*.json` | 動作確認・故障再現資料。正式V3観測の母集団には入れない |
| D | M：`results/final/deterministic_prototype*.json`、rejected/aborted Gemini artifacts | 合成・旧契約・失敗の資料。完成研究へ昇格しない |
| D | 旧branch・backup内の旧tuple境界、旧表示生成物 | 未修正版を最新実装に混ぜない。削除せず履歴として参照 |

`homeostasis_core/engine.py` の一般化TurnEngineと実Gemini runnerは別経路。クラス名だけで現在の実行順序を説明しない。研究branch全体をmainへmergeして継承する案は採らない。

## 保存済みrunの確認

Rの `results/status/runs/<run_id>/` のsanitized JSONを読んだ値：

| run_id | 保存状態 | TURN | audit上calls / retry | research eligible | 用途 |
| --- | --- | --- | --- | --- | --- |
| 20260917T075421Z-11147417 | success | 8 | 80 / 0 | true | C：最初の完全世界線 |
| 20260917T071205Z-fb7f949f | failed | 2 | 29 / 0 | false | D：混合受取容量故障 |
| 20260917T004355Z-c09ce05c | failed | 0 | 1 / 0 | false | D：transport入口故障 |
| 20260917T022330Z-a9d78ed9 | success / probe | 0 | 1 / 0 | false | D：入口確認 |

ここでcallsは保存auditの計数。入口故障の1 attemptを、Geminiサーバーが処理・課金した1回答と断定しない。
完全runのcontracts / decision audit / transport audit / secret scanはいずれも保存値PASS。
そのruntimeのsource commitは `c434a660220b1720fe8c4c10ee836f3e587e0259`。保管branch RのHEADと混同しない。原本result SHA256は `c8c82ede050988629fd4c386a9dac7c40fab2c39162581ee5124bf679eaed926`。

[完全run observation](https://github.com/ryoryo3888/homeostasis-security/blob/ed70ee235c4ce098709c0825d055e4b64f901db8/results/status/runs/20260917T075421Z-11147417/e0919357163de85576e395a5fb9128896028140841c6870902d120dc14a5dbf7.json)のTURN4は、**全決済要求356／実現56／未実現300**。よく引用される350／50／300は7国家の同一支援先要求という部分集合であり、TURN全体ではない。V3の集計にも対象集合・単位を必須にする。

失敗run #2の保存診断では、個別schemaを通った複数行動が受取余地を二重使用した。SMALLは最後の回答者であり故障主体とは限らない。`failure.agent_id` と `failure.stage` を分ける必要がある。詳しくはRの `docs/audits/20260917T071205Z-failure-diagnosis.md`。

## 8国家の既存設定

R：`config/country_archetypes.json` の実値。順序は **food / fossil / renewable / nuclear / grid-storage / funds / logistics**。全て0〜100の正規化値であり実物量ではない。

| ID・特性 | 初期資源7値 | 設定された利益・傾向 | sample network上の需要／関係 |
| --- | --- | --- | --- |
| MIL 軍事大国 | 68 / 70 / 55 / 82 / 78 / 84 / 88 | 安全保障・影響力、外交姿勢58 | FRAGILEへlogistics供給 |
| RES 資源輸出国 | 72 / 96 / 67 / 40 / 70 / 78 / 82 | 輸出収入・供給路、外交姿勢55 | FOODへfossil供給 |
| FOOD 食料輸入国 | 42 / 58 / 60 / 45 / 64 / 70 / 74 | 食料・物流、外交姿勢72 | food20/turn、fossil14/turn。NEUTRAL/ECON/RES依存 |
| SMALL 小国 | 58 / 48 / 66 / 18 / 55 / 58 / 62 | 主権・交易、外交姿勢80 | renewable8/turn。ISLAND依存 |
| ISLAND 島嶼国 | 50 / 42 / 82 / 20 / 70 / 62 / 55 | 海上物流・気候、外交姿勢84 | SMALLへrenewable供給 |
| ECON 経済大国 | 75 / 65 / 86 / 84 / 90 / 98 / 94 | 市場・資金循環、外交姿勢76 | FOODへfood、FRAGILEへfunds供給 |
| FRAGILE 紛争脆弱国 | 35 / 32 / 40 / 10 / 30 / 35 / 28 | 国内安定・人道、外交姿勢46 | funds10/turn、logistics8/turn。ECON/MIL依存 |
| NEUTRAL 中立国 | 88 / 62 / 88 / 80 / 86 / 82 / 86 | 中立・仲介、外交姿勢95 | FOODへfood供給 |

需要未設定の国を「需要なし」と一般化しない。外交姿勢は行動の確定脚本ではない。profileの `allowed_actions` は日本語役割記述で、実Gemini経路の実行可能catalogueを制限するenumではない。利益全文も現payloadにすべて渡るとは限らない。実payloadはprivate view、proposal、履歴、数値decision factors、catalogueを使用する。

実行可能行動は共通11種：PROVIDE_RESOURCE / DRAW_WORLD_POOL / SUPPORT_LOGISTICS / PROVIDE_FUNDS / RESTRICT_EXPORTS / SUSPEND_SUPPLY / DISRUPT_LOGISTICS / DEFENSIVE_ESCORT / MEDIATE / PROTECT_RESERVES / NO_ACTION。資源・経路・上限で選択肢が変わる。応答はACCEPT / REJECT / CONDITIONALのみで、別案交渉の独立protocolはまだない。

不足：全国家の需要根拠、二国間trust、地理的距離、保管・輸送所有権、経路代替、取引相手の同意、継続契約、投入産出依存、能力の回復費用。V3でも現実地理や同盟を勝手に割り当てない。同じ外交傾向でもstock・被害・依存・選択肢が違う比較を可能にする。

## 実装から確認した境界

- `resources.process_resource_network`：供給予定×capacity率×reliability率を、開始在庫と受入余地で比例制約。需要を消費するが、不足指標は需要−**入荷**で、開始備蓄を含まない。消費不足と輸入不足は同一ではない。
- `feasibility.feasible_actions`：network未指定時は全対全の代替経路を作る。V3 network必須モードでは暗黙fallbackを禁止する設計。
- `settle_atomic_actions`：poolは開始残高のみ引出し可能。同TURN拠出や送出で生じる余地は再利用しない。直接援助とpool受取は共通headroomを使う。比例配分は最大流ではない。
- `resolve_conditional_participants`：ACCEPT/CONDITIONAL集合から同時に不成立候補を除去する最大固定点。相互参加の循環は成立可能。minimum_aid_amountは自己の選択量、mutual_performanceは他の参加者の存在、burdenは自己申告値。実現援助保証ではない。
- `apply_structured_actions`：atomicな任意行動の後に設定networkの自動供給・消費。二つの配分段階を一つの共有容量ledgerで管理してはいない。参加数や選択行動数もtrust等に影響するため、効果をすべて実現物量の因果と読めない。
- `reconstruction_step`：国内capacityと実現援助から被害量を減らすが、復興用途の資源消費を同じ関数で引き落とさない。ton被害と正規化援助の重みはモデル仮定。
- `derive_event`：閾値・priority・直近2イベントcooldownによる候補選択。固定TURN脚本ではないが、自由生成の社会現象でもない。タイトルの「価格圧力」に価格市場モデルはない。
