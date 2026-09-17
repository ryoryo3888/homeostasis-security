# 8TURN直前無料ゲート — 20260917T001606Z-c7bae18f

保存済みfresh 1TURNとコードの確認。今回のGemini/有料API callsは0。probe/1TURN/8TURNの実験起動なし。無料テスト内のmockは実API実験と区別する。

## 保存済み実行の検証

- 検査時branch: choice-id-one-turn-probe-20260917。HEAD: 33da81e4bf8695888b19e63818f2eff678f6b28d。d37dfcfの同時条件決済修正を含む。
- 1TURN完走。保存transportは10/10 calls、全attempt=1、全returned、retry=0。
- 調整機関1・国家8・Evaluator1。8国家のchoice→action契約、decision/transportの識別子対応、再読込監査、secret scanはPASS。
- 全8国家の成立集合・atomic settlement・正式world・研究指標・復興値は修正版apply_structured_actionsとreconstruction_stepの無料再現に完全一致。
- Evaluatorのexecuted_true_stateは正式な決済直後状態に完全一致。runnerが後で追加するreconstructionも別途一致を確認。
- 同じ回答集合を旧方式で評価するとFRAGILEのみ。保存結果は全8国家成立なので旧方式とは不一致。実行時ソースの署名は元runにないため、現HEADの修正継承と保存結果の完全再現を根拠とする。
- 既存runは変更せず、result/result.audit/transport.auditのSHA-256を機械可読ゲート記録に保存。

## 8TURN実行契約のコード確認

- research_workflow.PLANS.experiment: 1世界線、8TURN、最大80 API calls。BoundedClientが送信前に試行を永続記録し、上限到達後の送信を拒否。
- gateway retry_limit=1は総試行数1の意味。SDK HttpRetryOptions(attempts=1)。再試行0。
- validation失敗はRuntimeErrorとなりrun_liveから伝播。後続Agent/TURNへ進まず、workflowがrejected配下にfailureを保存。監査保存失敗も停止。
- TURN2以降はderive_eventに直前の正式world・action_counts・history_state・直近イベント履歴を渡す。event_candidatesは資源/経済/信頼/緊張/需要不足/行動から優先度を計算し、cooldownを適用する。イベント語彙は定義済みだが、TURN番号に対応した固定シナリオではない。
- validate_researchは1世界線8TURN完走、80件の対応する監査、契約、状態連続性、派生イベント、復興値を確認。不完全run・監査不成立・全TURN回答収束は研究採用しない。
- researchへの移動は実験完走後のeligibility判定が成功した場合のみ。今回の1TURNはresearch対象外のまま。

結果・最終make checkは [development state](../../results/status/development.json) を一次情報とする。8TURN READYは実行許可ではなく、別途明示的な許可が必要。
