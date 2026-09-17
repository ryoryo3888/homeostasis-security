# ChatGPT直接観測

最初に [開発・監査状態](results/status/development.json) を読む。確認できた最新保存runはprobe `20260917T022330Z-a9d78ed9`（PASS、1試行、retry 0）。申告された新fresh 1TURNは未発見で、8TURN READY: NO。以前の1TURNやprobeを今回のfresh 1TURNと取り違えない。今後は明示許可した実験の成功・失敗後にremote照合まで自動同期する。

続いてこの作業ブランチの [results/status/latest.json](results/status/latest.json) を読む。

- Repository: `ryoryo3888/homeostasis-security`
- Branch: `choice-id-one-turn-probe-20260917`（mainとは異なる）
- GitHub API: `https://api.github.com/repos/ryoryo3888/homeostasis-security/contents/results/status/latest.json?ref=choice-id-one-turn-probe-20260917`
- Raw: `https://raw.githubusercontent.com/ryoryo3888/homeostasis-security/choice-id-one-turn-probe-20260917/results/status/latest.json`

`latest` から最新probe・turn・experiment・successful_research・failed_or_rejectedへ進む。値がnullならその種別の公開済みrunはない。`history_index` は検証済み履歴と公開を拒否したrunの一覧。`latest_observed_run` が新しくても `latest_blocked_run` があれば、そのrunのログは公開できていない。過去の成功を最新成功と取り違えない。

各runの公開JSONには次を含む。

- `decisions`: 公開の最終回答、choice_id / amount / reason、materialized_action、recipient / resource、契約検証、run / turn / agent / attempt / call_id。元のカタログから再復元できる。
- `transport_audit`: 実試行数、上限、各decisionとの識別子対応。API callsは過去runの消費、`publication_api_calls: 0` は今回の公開処理の消費。
- `worlds`: 実際に完了したTURNだけ。world、research_metrics、country_states、resources、world_pool、reconstruction、成立行動・同時決済・イベント・履歴。global_homeostasisはworld/metrics、sovereigntyはresearch_metrics.national_sovereignty、trustはworld.international_trust、緊張指標はworld.conflict_load。未完了TURNの数値は作らない。
- `failure`: 停止Agent・TURN・何call目・validation・error_type。古い監査に具体的エラーがなければnull。`derived_diagnosis` は保存済み構造からの機械判定であり、モデルの新しい回答ではない。
- `validation.research_eligible`: 正式研究採用の可否。probe、途中失敗、研究不採用runはfalse。`latest.successful_research` から正式結果に限って辿る。

`result_paths` の `#/...` は同じJSON内の項目を指す。ローカルのresults/probe・rejected・researchやcheckpointは非公開原本で、GitHubではresults/statusの検証済みコピーを読む。V1/V2や既存results/finalの分類・データは変更していない。

契約FAILと監査FAILを区別する。例えばモデルが空のCONDITIONALを返して安全停止したrunは、contracts=FAILでもdecision_audit=PASSになり得る。壊れた監査・秘密情報を含むrunは公開ログを作らず、索引に固定の拒否コードだけを残す。旧probeの欠けたchoice-IDを逆算で埋めない。

現在地はmachine stateを一次情報とし、RESEARCH_STATE.md冒頭の生成欄と一致を検証する。その下は過去時点の記録。`commit` は生成時のソースHEADであり、公開ファイルを含むコミット自身ではない。`source_digest` は未コミット変更を含む検証対象コードの指紋。`updated_at` とGitHubの公開コミットを確認し、未同期のローカルrunが見えていると思い込まない。

## 利用者の通常工程

実験の成功・失敗後、検証・status生成・観測ファイルのcommit・現在branchへのpush・fetch後のremote HEAD照合まで自動実行される。`make publish-status` でも検証・secret scan・公開ファイル準備ができる。ここまでではGitHubは更新されない。

同期だけを再試行する操作は **`make sync-status`**。必要な無料check → 公開準備 → 再検証 → 観測ファイルだけcommit → 現在branchへpush → fetch/HEAD照合。実験は再実行しない。main/masterは禁止。他のstaged変更があれば停止する。実験/API呼び出しはしない。以後「終わった」「確認して」とChatGPTへ伝えれば、上記GitHubから読み取れる。

初回clone後は `git config --local core.hooksPath .githooks` で同梱pre-push検証を有効化できる。push対象コミットそのものの公開ファイル、秘密情報、原本の誤登録を検査する。Actionsでも `make check` と `make verify-status` を実施する。通常のGit操作を意図的に強制回避することまで保証する仕組みではない。

研究上、単一runから一般化・因果効果の断定をしない。理由は公開の行動説明だけであり内部推論ではない。観測完了は次の有料実験の許可ではない。次の実行は `next_step` と失敗理由を確認し、明示許可を得た最小段階だけにする。

[自動公開の仕様と今回の調査](docs/REMOTE_PUBLICATION.md)。現在の評価はdevelopment stateを優先し、未発見のfresh 1TURNを成功扱いしない。
