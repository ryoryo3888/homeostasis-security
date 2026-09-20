# リポジトリ案内・保管一覧

現行の入口、観測データ、過去資料を区別するための案内です。
現行の入口と実験データは従来の場所に保持し、使われていない過去画面の控え26件と
Pythonの控え9件を[archive](../archive/README.md)へ移しました。rootのファイルは137件から102件へ減っています。
移動した35件の内容はすべて同一で、旧パス・新パス・ハッシュを[移動台帳](../archive/manifest.json)に残しています。
現行V1〜V4の公開URLは維持しています。旧バックアップの単独URLは移動対象です。

## 現在の版と実装の対応

| 公開名 | 保存済み画面・データ | 実装の入口 | 注意点 |
| --- | --- | --- | --- |
| V1 二国間の恒常性 | [画面](../dashboard_v1.html)、[実験台帳](../research/experiments/registry.json)、[集計](../summary.json) | [simulation.py](../simulation.py)、[experiment_runner.py](../experiment_runner.py) | 16条件36 run。代表表示との二重計上をしない |
| V2 地球規模の恒常性 | [画面](../dashboard_v2.html)、[5ターンの記録](../v2_first_run.json) | [simulation_v2.py](../simulation_v2.py) | 保存結果の閲覧を維持。未承認の世界更新を補わないため新規実行は停止 |
| V3 自由対話 | [画面](../results/v2-five-runs/index.html)、[表示用データ](../results/v2-five-runs/data.json) | [v2_dialogue.py](../v2_dialogue.py)、[v2_autonomous.py](../v2_autonomous.py) | 旧v2名を維持。表示用データを全通信の生ログと同一視しない |
| V4 相互依存 | [画面](../dashboard_v4.html)、[保存検証例](../ui/v3/validation/) | [homeostasis_v4](../homeostasis_v4/)、[homeostasis_v3](../homeostasis_v3/)、[ローカル実行器](../tools/run_v4_local.py) | 検証例は実LLMの研究runではない。自由対話と既存の有限資源ルールを接続 |

V4の`homeostasis_v3/`、`scenarios/v3/`、`tests/v3/`、`ui/v3/`は内部の継続名です。
[番号整理の決定](architecture/VERSION_NUMBERING_REVISION.md)では内部識別子、旧URL、
履歴データとハッシュを保持しています。数字だけを一括置換しないでください。
`tests/final/`にも現在使われる応答処理・V1修復・自由対話のテストがあります。
フォルダ名だけを根拠に旧式・不要とは判断できません。今回の移動対象は現行の読み込み先から参照されない控えに限定しています。

## 目的ごとの作業場所

| 目的 | 場所 |
| --- | --- |
| Agentへ実際に渡す指示・私的情報の境界を確認 | [V4対話](../homeostasis_v4/dialogue.py)、[観測の透明化](architecture/OBSERVATION_TRANSPARENCY.md) |
| 世界の初期条件・輸送と資源の成立処理を確認 | [scenarios/v3](../scenarios/v3/)、[turn.py](../homeostasis_v3/turn.py)、[physical.py](../homeostasis_v3/physical.py)、[settlement.py](../homeostasis_v3/settlement.py) |
| 無料ローカルLLMの小規模試行 | [LOCAL_PILOT](architecture/LOCAL_PILOT.md)、[local_observation.py](../homeostasis_v4/local_observation.py) |
| Gemini観測・継続の既存入口 | [run_v4_observation.py](../tools/run_v4_observation.py)、[continue_v4_observation.py](../tools/continue_v4_observation.py)、[extend_v4_observation.py](../tools/extend_v4_observation.py) |
| 実験記録の形式・照合 | [EVIDENCE_FORMAT](architecture/EVIDENCE_FORMAT_V1.md)、[evidence.py](../homeostasis_v4/evidence.py)、[verify_evidence.py](../tools/verify_evidence.py) |
| 無料検証 | [Makefile](../Makefile)、[run_free_tests.py](../tools/run_free_tests.py)、[requirements](../requirements/) |
| V1・V2画面の生成 | [build_ui_previews.py](../tools/build_ui_previews.py) |
| V3自由対話の画面生成 | [build_v2_observation.py](../tools/build_v2_observation.py) |
| V4画面の生成 | [build_v3_candidate.py](../tools/build_v3_candidate.py)、[build_v3_earth.py](../tools/build_v3_earth.py) |
| 画面の固定範囲と検証 | [Visual Constitution](architecture/HOMEOSTASIS_VISUAL_CONSTITUTION.md)、[tests/layout](../tests/layout/)、[ui](../ui/) |
| 旧final系統の実装・監査 | [homeostasis_core](../homeostasis_core/)、[config](../config/)、[results/final](../results/final/) |

`homeostasis_core/`内には現行実行器からも使う実行ロック等の共通部品があります。
旧系統に関係するディレクトリ全体を停止・移動する整理は行っていません。
現時点のソースを読むことと、そのソースが過去のrunを生成したと証明することは別です。

## 実験記録と保管物

- **登録済みの元データ**：V1・V2は[台帳](../research/experiments/README.md)と
  [照合一覧](../research/experiments/artifact_allowlist.json)で確認します。
  ファイル名に`previous`がある結果も、V1の36 runに含まれています。
- **集計・表示用データ**：`summary.json`、`summary.csv`、自由対話ページの`data.json`等は
  原記録から集計・抽出したものです。原記録の代わりに上書きしません。
- **検証例**：`ui/v3/validation/`は動作検証用です。実Agentの観測数に足しません。
- **旧結果・失敗・中間物**：`results/final/`の監査記録・checkpoint、rootの未登録JSON、
  `contrast_backup/`等を保持します。未登録は「捨ててよい」という意味ではありません。
- **新しいローカルrun**：取得するrunごとに独立した出力先を使い、`manifest.json`、
  `RAW/`、`terminal.json`、`DERIVED/`を[既存形式](architecture/EVIDENCE_FORMAT_V1.md)で保存します。
  実行・照合後に公開対象を確認し、失敗も含めて保存します。開発相談チャットは研究生ログに含めません。

## rootの保管一覧（整理時点）

調査対象はcommit `c7c0faad77f80a2c05bd412c68f69159d7b89782`の追跡済みrootファイル137件です。
以下で整理前の全件を重複なく分類し、移動対象は新しい保管先へリンクしています。追跡されていないローカルファイルは対象外です。
うち112件は[過去の保護用ハッシュ一覧](../tests/layout/protected-baseline.sha256)にも名前があります。
この過去一覧と、現在の画面検証に使う[承認済みソース基準](../tests/layout/source_baseline.json)は別です。
本分類は所在案内であり、実験の採用可否や実行時の来歴を新たに認定するものではありません。
READMEの更新に伴う照合値の変更は、台帳の非実験資料であるREADMEの1件だけです。
実験結果・現行画面・過去の照合値は変更していません。保護用の検証は移動台帳を参照して旧内容との一致を確認します。

<details>
<summary>公開画面・互換入口・画面検証 — 8件</summary>

- [dashboard_v1.html](../dashboard_v1.html)
- [dashboard_v2.html](../dashboard_v2.html)
- [dashboard_v3.html](../dashboard_v3.html)
- [dashboard_v4.html](../dashboard_v4.html)
- [index.html](../index.html)
- [preview_v1_unified.html](../preview_v1_unified.html)
- [preview_v2_unified.html](../preview_v2_unified.html)
- [ui_compare_preview.html](../ui_compare_preview.html)

</details>

<details>
<summary>画面資産・発表資料 — 9件</summary>

- [a_high_tech_sci_fi_dashboard_style_user_interface.png](../a_high_tech_sci_fi_dashboard_style_user_interface.png)
- [earth_japan_network.png](../earth_japan_network.png)
- [earth_japan_network_v2.png](../earth_japan_network_v2.png)
- [homeostasis-research-integration.js](../homeostasis-research-integration.js)
- [homeostasis-research-layer.css](../homeostasis-research-layer.css)
- [homeostasis-research-layer.js](../homeostasis-research-layer.js)
- [homeostasis-ui-system.css](../homeostasis-ui-system.css)
- [homeostasis_security_presentation(2).pptx](../homeostasis_security_presentation%282%29.pptx)
- [presentation.html](../presentation.html)

</details>

<details>
<summary>V1の実行・条件・テスト — 4件</summary>

- [experiment_runner.py](../experiment_runner.py)
- [reaction_axis_config.json](../reaction_axis_config.json)
- [simulation.py](../simulation.py)
- [test_simulation.py](../test_simulation.py)

</details>

<details>
<summary>V2の保存版に関する実装・テスト — 2件</summary>

- [simulation_v2.py](../simulation_v2.py)
- [test_simulation_v2.py](../test_simulation_v2.py)

</details>

<details>
<summary>現在のV3自由対話の実装（旧v2名） — 6件</summary>

- [v2_autonomous.py](../v2_autonomous.py)
- [v2_continue_pilot.py](../v2_continue_pilot.py)
- [v2_dialogue.py](../v2_dialogue.py)
- [v2_finish_pilot.py](../v2_finish_pilot.py)
- [v2_paid_pilot.py](../v2_paid_pilot.py)
- [v2_repeat_pilot.py](../v2_repeat_pilot.py)

</details>

<details>
<summary>応答処理・記録の共通部品 — 4件</summary>

- [model_response_json.py](../model_response_json.py)
- [provider_response.py](../provider_response.py)
- [provider_retry.py](../provider_retry.py)
- [response_receipts.py](../response_receipts.py)

</details>

<details>
<summary>旧final系統（現行V4の入口ではない） — 4件</summary>

- [analyze_emergent_worldlines.py](../analyze_emergent_worldlines.py)
- [dashboard_final.html](../dashboard_final.html)
- [final_experiment_runner.py](../final_experiment_runner.py)
- [simulation_final.py](../simulation_final.py)

</details>

<details>
<summary>登録済みの元データ（V1 36件・V2 1件） — 37件</summary>

- [result_cautious_hardliner_law_hotline_run1.json](../result_cautious_hardliner_law_hotline_run1.json)
- [result_cautious_hardliner_law_hotline_run2.json](../result_cautious_hardliner_law_hotline_run2.json)
- [result_cautious_hardliner_law_no_hotline_run1.json](../result_cautious_hardliner_law_no_hotline_run1.json)
- [result_cautious_hardliner_law_no_hotline_run2.json](../result_cautious_hardliner_law_no_hotline_run2.json)
- [result_cautious_hardliner_no_law_hotline_run1.json](../result_cautious_hardliner_no_law_hotline_run1.json)
- [result_cautious_hardliner_no_law_hotline_run2.json](../result_cautious_hardliner_no_law_hotline_run2.json)
- [result_cautious_hardliner_no_law_no_hotline_run1.json](../result_cautious_hardliner_no_law_no_hotline_run1.json)
- [result_cautious_hardliner_no_law_no_hotline_run2.json](../result_cautious_hardliner_no_law_no_hotline_run2.json)
- [result_cautious_no_law_hotline_run1.json](../result_cautious_no_law_hotline_run1.json)
- [result_cautious_no_law_hotline_run2.json](../result_cautious_no_law_hotline_run2.json)
- [result_cautious_no_law_no_hotline_run1.json](../result_cautious_no_law_no_hotline_run1.json)
- [result_cautious_no_law_no_hotline_run2.json](../result_cautious_no_law_no_hotline_run2.json)
- [result_hardliner_cautious_law_hotline_run1.json](../result_hardliner_cautious_law_hotline_run1.json)
- [result_hardliner_cautious_law_hotline_run2.json](../result_hardliner_cautious_law_hotline_run2.json)
- [result_hardliner_cautious_law_no_hotline_run1.json](../result_hardliner_cautious_law_no_hotline_run1.json)
- [result_hardliner_cautious_law_no_hotline_run2.json](../result_hardliner_cautious_law_no_hotline_run2.json)
- [result_hardliner_cautious_no_law_hotline_run1.json](../result_hardliner_cautious_no_law_hotline_run1.json)
- [result_hardliner_cautious_no_law_hotline_run2.json](../result_hardliner_cautious_no_law_hotline_run2.json)
- [result_hardliner_cautious_no_law_no_hotline_run1.json](../result_hardliner_cautious_no_law_no_hotline_run1.json)
- [result_hardliner_cautious_no_law_no_hotline_run2.json](../result_hardliner_cautious_no_law_no_hotline_run2.json)
- [result_hardliner_law_hotline_run1.json](../result_hardliner_law_hotline_run1.json)
- [result_hardliner_law_hotline_run2.json](../result_hardliner_law_hotline_run2.json)
- [result_hardliner_law_no_hotline_run1.json](../result_hardliner_law_no_hotline_run1.json)
- [result_hardliner_law_no_hotline_run2.json](../result_hardliner_law_no_hotline_run2.json)
- [result_hardliner_no_law_hotline_run1.json](../result_hardliner_no_law_hotline_run1.json)
- [result_hardliner_no_law_hotline_run2.json](../result_hardliner_no_law_hotline_run2.json)
- [result_hardliner_no_law_no_hotline_run1.json](../result_hardliner_no_law_no_hotline_run1.json)
- [result_hardliner_no_law_no_hotline_run2.json](../result_hardliner_no_law_no_hotline_run2.json)
- [simulation_result_cautious_cautious_law_hotline_run1.json](../simulation_result_cautious_cautious_law_hotline_run1.json)
- [simulation_result_cautious_cautious_law_hotline_run1_previous_20260830T105924.json](../simulation_result_cautious_cautious_law_hotline_run1_previous_20260830T105924.json)
- [simulation_result_cautious_cautious_law_hotline_run2.json](../simulation_result_cautious_cautious_law_hotline_run2.json)
- [simulation_result_cautious_cautious_law_hotline_run3.json](../simulation_result_cautious_cautious_law_hotline_run3.json)
- [simulation_result_cautious_cautious_law_hotline_run4.json](../simulation_result_cautious_cautious_law_hotline_run4.json)
- [simulation_result_cautious_cautious_law_no_hotline_run1.json](../simulation_result_cautious_cautious_law_no_hotline_run1.json)
- [simulation_result_cautious_cautious_law_no_hotline_run2.json](../simulation_result_cautious_cautious_law_no_hotline_run2.json)
- [simulation_result_cautious_cautious_law_no_hotline_run3.json](../simulation_result_cautious_cautious_law_no_hotline_run3.json)
- [v2_first_run.json](../v2_first_run.json)

</details>

<details>
<summary>集計・比較資料 — 9件</summary>

- [contrast_evidence.md](../contrast_evidence.md)
- [contrast_misperception.png](../contrast_misperception.png)
- [contrast_resilience.png](../contrast_resilience.png)
- [contrast_rubric.md](../contrast_rubric.md)
- [contrast_tension.png](../contrast_tension.png)
- [contrast_trust.png](../contrast_trust.png)
- [redraw_contrast_dark.py](../redraw_contrast_dark.py)
- [summary.csv](../summary.csv)
- [summary.json](../summary.json)

</details>

<details>
<summary>台帳未登録のJSON（旧結果・バックアップ・中間評価） — 16件</summary>

- [contrast_scores.json](../contrast_scores.json)
- [contrast_scores_hotline.json](../contrast_scores_hotline.json)
- [contrast_scores_no_hotline.json](../contrast_scores_no_hotline.json)
- [simulation_result.json](../simulation_result.json)
- [simulation_result_backup.json](../simulation_result_backup.json)
- [simulation_result_before_rich_data.json](../simulation_result_before_rich_data.json)
- [simulation_result_demo_gemini.json](../simulation_result_demo_gemini.json)
- [simulation_result_development.json](../simulation_result_development.json)
- [simulation_result_independent_agents_hotline.json](../simulation_result_independent_agents_hotline.json)
- [simulation_result_independent_agents_hotline_backup.json](../simulation_result_independent_agents_hotline_backup.json)
- [simulation_result_independent_agents_hotline_final.json](../simulation_result_independent_agents_hotline_final.json)
- [simulation_result_independent_agents_no_hotline.json](../simulation_result_independent_agents_no_hotline.json)
- [simulation_result_independent_agents_no_hotline_backup.json](../simulation_result_independent_agents_no_hotline_backup.json)
- [simulation_result_independent_agents_no_hotline_before_final_run.json](../simulation_result_independent_agents_no_hotline_before_final_run.json)
- [simulation_result_independent_agents_no_hotline_failed_backup.json](../simulation_result_independent_agents_no_hotline_failed_backup.json)
- [simulation_result_independent_agents_no_hotline_final.json](../simulation_result_independent_agents_no_hotline_final.json)

</details>

<details>
<summary>過去画面の保管 — 26件（archiveへ移動済み）</summary>

- [dashboard_before_arrow_fix.html](../archive/legacy-pages/dashboard_before_arrow_fix.html)
- [dashboard_before_contrast_ui.html](../archive/legacy-pages/dashboard_before_contrast_ui.html)
- [dashboard_before_dynamic_metrics.html](../archive/legacy-pages/dashboard_before_dynamic_metrics.html)
- [dashboard_before_earth_motion.html](../archive/legacy-pages/dashboard_before_earth_motion.html)
- [dashboard_before_impact_fix.html](../archive/legacy-pages/dashboard_before_impact_fix.html)
- [dashboard_before_layout_repair.html](../archive/legacy-pages/dashboard_before_layout_repair.html)
- [dashboard_before_signal_pulse.html](../archive/legacy-pages/dashboard_before_signal_pulse.html)
- [dashboard_before_turn_labels.html](../archive/legacy-pages/dashboard_before_turn_labels.html)
- [dashboard_before_worldtext_fix.html](../archive/legacy-pages/dashboard_before_worldtext_fix.html)
- [dashboard_experiments_restored_v8.html](../archive/legacy-pages/dashboard_experiments_restored_v8.html)
- [dashboard_final_working.html](../archive/legacy-pages/dashboard_final_working.html)
- [dashboard_reason_test.html](../archive/legacy-pages/dashboard_reason_test.html)
- [dashboard_v1_before_belief_fix.html](../archive/legacy-pages/dashboard_v1_before_belief_fix.html)
- [dashboard_v1_before_chart_fix.html](../archive/legacy-pages/dashboard_v1_before_chart_fix.html)
- [dashboard_v1_before_chart_fix2.html](../archive/legacy-pages/dashboard_v1_before_chart_fix2.html)
- [dashboard_v1_before_concern_fix.html](../archive/legacy-pages/dashboard_v1_before_concern_fix.html)
- [dashboard_v1_before_data_bind.html](../archive/legacy-pages/dashboard_v1_before_data_bind.html)
- [dashboard_v1_before_earth_image.html](../archive/legacy-pages/dashboard_v1_before_earth_image.html)
- [dashboard_v1_before_json_fix.html](../archive/legacy-pages/dashboard_v1_before_json_fix.html)
- [dashboard_v1_before_paid_run.html](../archive/legacy-pages/dashboard_v1_before_paid_run.html)
- [dashboard_working_complete.html](../archive/legacy-pages/dashboard_working_complete.html)
- [dashboard_working_final_ui.html](../archive/legacy-pages/dashboard_working_final_ui.html)
- [index.html.txt](../archive/legacy-pages/index.html.txt)
- [index_before_earth_ui.html](../archive/legacy-pages/index_before_earth_ui.html)
- [index_before_globe_core.html](../archive/legacy-pages/index_before_globe_core.html)
- [index_failed_globe_trial.html](../archive/legacy-pages/index_failed_globe_trial.html)

</details>

<details>
<summary>過去Pythonの保管 — 9件（archiveへ移動済み）</summary>

- [simulation_backup.py](../archive/legacy-python/simulation_backup.py)
- [simulation_before_belief_update.py](../archive/legacy-python/simulation_before_belief_update.py)
- [simulation_before_concern_fix.py](../archive/legacy-python/simulation_before_concern_fix.py)
- [simulation_before_contrast_experiment.py](../archive/legacy-python/simulation_before_contrast_experiment.py)
- [simulation_before_independent_agents.py](../archive/legacy-python/simulation_before_independent_agents.py)
- [simulation_before_overall_impact.py](../archive/legacy-python/simulation_before_overall_impact.py)
- [simulation_before_paid_run.py](../archive/legacy-python/simulation_before_paid_run.py)
- [simulation_before_parser_fix.py](../archive/legacy-python/simulation_before_parser_fix.py)
- [simulation_before_quota_fix.py](../archive/legacy-python/simulation_before_quota_fix.py)

</details>

<details>
<summary>開発入口・管理 — 3件</summary>

- [.gitignore](../.gitignore)
- [Makefile](../Makefile)
- [README.md](../README.md)

</details>
