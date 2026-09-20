# 未登録JSON16件の追加調査

2026-09-20、`a47f155f543c38ccd48487055b45eb606364f708`時点のrootに残る
未登録JSON16件を確認しました。現行参照5件と固有の過去記録5件は元の場所に保持し、
完全な重複4件と中間集計2件だけを内容そのままで保管先へ移しました。
初回40件を含めて保管は46件、rootの追跡ファイル数は102件から96件になります。

これはファイル整理の調査です。実験台帳への採用、成功判定、当時のモデル実行の証明は行っていません。
V1の登録済み36 run・V2の保存結果・現行V1〜V4の画面と実行コードは変更していません。

## 16件の判断

| 元のファイル名 | 分類・扱い | 確認した理由 |
| --- | --- | --- |
| `contrast_scores.json` | 現行参照・保持 | `redraw_contrast_dark.py`の入力。統合した採点列を保持 |
| `simulation_result.json` | 現行参照・保持 | `index.html`の読込先 |
| `simulation_result_development.json` | 現行参照・保持 | `simulation.py`の開発モード出力先 |
| `simulation_result_independent_agents_hotline.json` | 現行参照・保持 | 実験条件から組み立てる出力先 |
| `simulation_result_independent_agents_no_hotline.json` | 現行参照・保持 | 実験条件から組み立てる出力先 |
| `simulation_result_backup.json` | 固有記録・保持 | 他と異なる5行の旧結果 |
| `simulation_result_independent_agents_hotline_backup.json` | 固有記録・保持 | 他と異なる5行の旧結果 |
| `simulation_result_independent_agents_no_hotline_backup.json` | 固有記録・保持 | `before_final_run`との重複組の保持側 |
| `simulation_result_independent_agents_no_hotline_failed_backup.json` | 固有記録・保持 | 失敗関連の名前を持つ独自記録。成功・失敗を再判定しない |
| `simulation_result_independent_agents_no_hotline_final.json` | 固有記録・保持 | `turn_count`は5だが`results`は1行。完走扱いにしない |
| `simulation_result_before_rich_data.json` | 完全重複・保管 | `simulation_result.json`と全バイト一致 |
| `simulation_result_demo_gemini.json` | 完全重複・保管 | `simulation_result.json`と全バイト一致 |
| `simulation_result_independent_agents_hotline_final.json` | 完全重複・保管 | `simulation_result_independent_agents_hotline.json`と全バイト一致 |
| `simulation_result_independent_agents_no_hotline_before_final_run.json` | 完全重複・保管 | `simulation_result_independent_agents_no_hotline_backup.json`と全バイト一致 |
| `contrast_scores_hotline.json` | 中間集計・保管 | `scores`と`scale`が統合集計のhotline側と一致 |
| `contrast_scores_no_hotline.json` | 中間集計・保管 | `scores`と`scale`が統合集計のno_hotline側と一致 |

固定文字列だけでなく、`simulation.py`の
`simulation_result_independent_agents_{EXPERIMENT_CONDITION}.json`という動的な出力名も確認しています。
`backup`・`final`という名前だけで、不要・成功・完走とは判断していません。

中間集計2件はAgentの発言原文ではなく旧比較の採点データです。採点列は
`contrast_scores.json`の`conditions.hotline`／`conditions.no_hotline`と一致しますが、
説明などを含むファイル全体の重複とは扱わず、そのまま保管しています。再採点や図の再生成はしていません。

## 保存と照合

- 完全重複4件の移動先：[duplicate-results](../archive/duplicate-results/)
- 中間集計2件の移動先：[legacy-derived](../archive/legacy-derived/)
- 16件の分類・内容ハッシュ・参照先：[調査データ](../research/experiments/unregistered_audit_20260920.json)
- 追加6件の移動元・移動先：[追加移動台帳](../archive/unregistered-json-moves.json)
- 初回40件の移動台帳：[初回台帳](../archive/manifest.json)（変更なし）

保護テストは移動台帳で置き場所を解決し、元の保護ハッシュと移動前commitの内容を照合します。
出所監査にも移動後の重複ファイルを含め、整理によって履歴が見えなくならないようにしています。
6件の旧root URLは変わります。現在使われる読込先・出力先は保持し、過去の配置は移動前commitから復元できます。
`mode: gemini`などの自己申告だけを根拠に、当時の実API実行を確認済みにはしません。
