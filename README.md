# HOMEOSTASIS SECURITY

HOMEOSTASIS SECURITYは、国家の安全保障反応を生体の免疫反応として捉え、脅威に対する反応が強すぎる「過剰反応」、おおむね釣り合う「適応反応」、弱すぎる「過少反応」をマルチエージェント・シミュレーションで観察するプロジェクトです。

目的は、国家タイプ、国際法、Hotline（直接対話経路）の違いが、脅威認知、防衛反応、エスカレーション圧、信頼、回復力にどう関連するかを探索することです。「緊張が低いほど常に良い」とはせず、高い脅威に対する必要な防衛反応も適応に含めます。

## Dashboard

- 公開Dashboard: <https://ryoryo3888.github.io/homeostasis-security/>
- Dashboard本体: <https://ryoryo3888.github.io/homeostasis-security/dashboard_v1.html?layout-final=1>

ローカルでも、追加ライブラリやAPIキーなしで保存済み結果を閲覧できます。

```bash
git clone https://github.com/ryoryo3888/homeostasis-security.git
cd homeostasis-security
python3 -m http.server 8000
```

起動後に <http://localhost:8000/dashboard_v1.html?layout-final=1> を開いてください。終了は `Ctrl+C` です。

## 16条件・36 runの比較

各runは8 TURNです。A国とB国の国家タイプ、国際法、Hotlineを組み合わせたA〜Pの16条件を比較しています。

| 条件 | A国 | B国 | 国際法 | Hotline | run数 |
|---|---|---|---:|---:|---:|
| A | 慎重外交型 | 慎重外交型 | ON | ON | 5 |
| B | 強硬型 | 強硬型 | ON | ON | 2 |
| C | 慎重外交型 | 慎重外交型 | OFF | ON | 2 |
| D | 慎重外交型 | 慎重外交型 | ON | OFF | 3 |
| E | 強硬型 | 強硬型 | OFF | OFF | 2 |
| F | 強硬型 | 強硬型 | OFF | ON | 2 |
| G | 強硬型 | 強硬型 | ON | OFF | 2 |
| H | 慎重外交型 | 慎重外交型 | OFF | OFF | 2 |
| I | 強硬型 | 慎重外交型 | ON | ON | 2 |
| J | 強硬型 | 慎重外交型 | ON | OFF | 2 |
| K | 強硬型 | 慎重外交型 | OFF | ON | 2 |
| L | 強硬型 | 慎重外交型 | OFF | OFF | 2 |
| M | 慎重外交型 | 強硬型 | ON | ON | 2 |
| N | 慎重外交型 | 強硬型 | ON | OFF | 2 |
| O | 慎重外交型 | 強硬型 | OFF | ON | 2 |
| P | 慎重外交型 | 強硬型 | OFF | OFF | 2 |

Aは5 run、Dは3 run、その他14条件は各2 runで、合計36 runです。Dashboard上部のシナリオ表示は各条件の代表runを読み込み、比較グラフと表は36 run全体の集計を表示します。

## 指標

`actual_threat_level` はEvaluatorによる推定脅威で、客観的な真実ではありません。各国・各TURNについて、次を計算します。

```text
reaction_gap = 反応強度 - 推定脅威
adaptive_fit = max(0, 100 - abs(reaction_gap))
```

現在の許容幅は±10です。`reaction_gap > 10`を過剰反応、`-10`以上`10`以下を適応反応、`reaction_gap < -10`を過少反応と分類します。

## Dashboardで観測された主な結果

以下は保存済み36 runについての記述的な観測結果です。

- 強硬型同士で国際法・HotlineともOFFのEは、過剰反応率87.5%、平均エスカレーション圧37.188、平均回復力68.375でした。16条件中、過剰反応率とエスカレーション圧が最も高く、回復力が最も低い条件です。
- 強硬型同士の比較では、Eに対してHotlineのみONのFはエスカレーション圧29.188・回復力75.062、国際法のみONのGは27.500・78.312、両方ONのBは24.562・81.500でした。今回の結果では、国際法やHotlineの存在がエスカレーション圧の低下と回復力の上昇に関連する方向が見られました。
- 強硬型を含む条件では過剰反応が増える傾向が見られました。ただし国家の配置や制度条件によって割合は異なり、強硬型を含むことだけで結果は決まりません。
- 慎重外交型同士でも、国際法ON・Hotline OFFのDでは過少反応率16.667%、国際法OFF・Hotline OFFのHでは12.5%でした。慎重さや低い緊張が、常に適応的な反応を意味するわけではありません。
- Hの平均`adaptive_fit`は94.719で16条件中最高でしたが、過少反応も観測されています。単一指標だけで条件の良否は判断できません。

## 安全な確認と再現手順

`experiment_runner.py` は、保存済みJSONを条件ごとに検出し、実験前に既存run数、上限到達状況、次の出力名を確認します。既存結果だけを安全に確認するには、次のdry-runを使います。

```bash
python3 experiment_runner.py dry-run
```

特定条件だけを確認する例です。

```bash
python3 experiment_runner.py dry-run --condition A
```

dry-runはGemini APIを呼ばず、ファイルも変更しません。現在はA〜Pの合計36 runを検出します。

保存済みJSONから集計を再生成する場合もGemini APIは使いません。ただし、次のコマンドは`summary.json`、`summary.csv`、`dashboard_experiments.html`を生成または更新します。変更のない確認だけが目的ならdry-runを使用してください。

```bash
python3 experiment_runner.py aggregate
```

新しい実験を行う場合のみ、`google-genai`とGemini APIキーが必要です。`run`は条件とseedを必須とし、既存runを確認した後、上限未満の場合だけ明示確認を経て1 runを実行します。

```bash
python3 experiment_runner.py run --condition B --seed 20260910
```

現在の保存済み結果は全条件が通常の2 run上限以上に達しているため、通常の`run`はAPI呼び出し前に停止します。APIキーはGitへ保存しないでください。

## seedと研究上の制約

36 run中26 runにはseedが記録されています。古いAの5 run、Dの3 run、Eの2 runにはseed記録がなく、合計10 runが未記録です。記録済みseedはPython側の乱数とGeminiの生成設定へ渡されていますが、外部モデルやサービス側の更新・実行差があるため、同じ文章や数値の完全再現は保証されません。公開結果の確認には保存済みJSONを使用してください。

本実験は条件ごとのrun数が少なく、A=5、D=3、その他=2と不均等です。結果は探索的・記述的なものであり、国際法やHotlineの因果効果、実世界への一般性を断定できません。また、推定脅威と反応強度はEvaluatorに依存し、許容幅±10も実証済みの普遍的基準ではありません。政策判断、国家評価、武力行使の正当化には使用できません。

## v2：地球規模の恒常性へ

HOMEOSTASIS SECURITY v1では、国家の安全保障行動を生命体の免疫反応として捉え、A国とB国の相互作用を通して、国際法・直通連絡・指導者特性などの条件が緊張の低下と恒常性回復へ与える影響を比較しました。

この二国間の安全保障における恒常性を比較した結果から、局所的には合理的な国家行動であっても、その影響が食料・経済・国際信頼などを通じて第三国へ波及し、地球全体では新たな不安定性を生む可能性に着目しました。

そこでv2では、研究対象を二国間から地球規模へ拡張し、次の問いを探ります。

> 国家主権を維持したまま、地球規模の恒常性は成立するのか？

### v1からv2への接続

v2は、v1とは切り離された別の作品ではありません。

v1の二国間シミュレーション第3ターンで発生した「A国のミサイルがB国の民間農地へ着弾」という局所イベントを起点として、農地被害、食料供給の低下、経済への影響、国際信頼の低下、紛争負荷の上昇が、第三国と地球全体へ波及する過程を扱います。

### v2第一版

v2第一版では、A国・B国・C国と、各国へ強制命令を行わない「地球調整機関」をAI Agentとして配置しました。

- A国：事件を発生させた国家
- B国：農地への直接被害を受けた国家
- C国：食料価格や経済への二次的影響を受ける第三国
- 地球調整機関：各国の主権を残したまま、地球全体の崩壊回避を試みる調整Agent
- Evaluator：各Agentから独立して世界状態を評価するAgent

Gemini Agentによる5ターンの実験では、各国と地球調整機関が状況を観測し、それぞれ独立して行動と提案への回答を判断します。その結果を、食料・エネルギー・経済・環境・国際信頼・紛争負荷・国家主権・地球全体の恒常性の推移として可視化します。

今回の実験では、国家主権を高い状態に維持しながら農地生産能力が回復し、地球全体の恒常性は68から82へ上昇しました。

### Dashboard

- [v1：二国間の恒常性](dashboard_v1.html?layout-final=1)
- [v2：地球規模の恒常性](dashboard_v2.html)

## 最終版：閉ループの地球恒常性研究

最終版はv1・v2を残した第三層です。局所事件を初期入力として、物理損傷、資源ネットワーク、国家ごとの非対称な認識、独立判断、地球調整機関の提案、成立した協力、独立Evaluator、次の因果イベントまでを複数ターン接続します。国家主権の維持と地球全体の恒常性を別々に測り、両者の衝突度も記録します。

実行は `python3 simulation_final.py`、複数runの保存前確認は `python3 final_experiment_runner.py OUTPUT.json --dry-run` です。保存処理は既存結果を上書きせず、seed、設定、コード版、Provider種別を記録します。画面は [最終版Dashboard](dashboard_final.html) から閲覧でき、「概要」「国家」「地球」「資源」「ログ／研究結果」に整理しています。

本実装は外部APIを使用しない決定論的Providerによる探索的研究です。同一seedと設定で再現できますが、モデル化されたAgent判断とEvaluatorは現実の国家意思決定を再現・予測するものではありません。指標、因果規則、認識誤差、統治成立条件はいずれも研究上の仮定を含みます。現実の政策判断、国家評価、国際法上の判断、制裁、緊急権限または武力行使の正当化には使用できません。将来は検証済みデータ、追加国家・シナリオ、差し替え可能なDecisionProviderによる比較研究へ拡張できます。

## 開発・実験の4段階（2026-09-17）

現在地は [RESEARCH_STATE.md](RESEARCH_STATE.md) を参照してください。新しい創発実験は以下の入口へ統一しています。

| コマンド | 通常の動作 | 明示実行時のAPI上限 | retry |
|---|---|---:|---:|
| `make check` | syntax・全unit tests・choice-ID・全契約・不正入力拒否・8TURNを無料検証 | 0 | 0 |
| `make probe` | 1 Agentの予定表示だけ | 1 | 0 |
| `make turn` | 1TURNの予定表示だけ | 10 | 0 |
| `make experiment` | 8TURN・1世界線の予定表示だけ | 80 | 0 |

`make check` はAPIキー不要・外部API 0 callsですが、実SDK境界テスト用に `requirements-gemini.txt` の依存が必要です（初回は `make setup-gemini`）。ネットワークをPython audit hookで遮断し、V1テスト用SDKも実クライアントを作れない代替にします。クラス形式と関数形式の全テストを実行します。成功時は `HOMEOSTASIS PREFLIGHT PASSED`、失敗時は `HOMEOSTASIS PREFLIGHT FAILED` と非ゼロ終了コードを返します。診断は `results/debug/check.json` に保存されます。

将来、課金実行を明示的に許可する場合だけ `CONFIRM=YES` を指定します。この指定でも先に無料チェックを再実行し、FAILならAPI接続前に停止します。SDKと環境内の認証情報は将来の実行時のみ必要です。キーの入力プロンプトは出しません。今回の作業では有料コマンドを実行していません。

1TURNは国家8 Agent＋地球調整機関＋Evaluatorの計10 Agentです。従来の「8国家の選択だけを確認するprobe」と異なり、資源決済・世界状態更新・復旧計算まで実行します。国家は `choice_id` と上限内の量を選び、Pythonがactionを復元・検証します。API例外や回答不正時は再試行せず停止し、送信前に試行数を永続記録します。旧probeとfinal runnerのCLI入口もこの安全な入口へ接続しています。V1の `experiment_runner.py` は互換性のため保持しています。

新規結果は `results/debug`、`results/probe`、`results/rejected`、`results/research` に分離します。既存JSON・Dashboard・`results/final`は移動しません。researchへの昇格は全TURN完走だけでなくschema・必要ログ・API監査・派生イベント・復旧計算・研究条件の検証が必要です。Dashboard用の正式結果列挙関数は `accepted_research_paths` です。今回Dashboardの読込経路は変更していません。

旧V1/V2と決定論的prototypeの固定復旧は保存済み研究の再現・互換性のため残っています。新しいpreflightとGemini実験はこれらの復旧表を使いません。互換テストの旧シナリオは `c918dd1` の親コミットから保存した `tests/fixtures/scenario_v1_legacy.json` を使用します。

### Gemini SDKのローカル依存関係

Makefileはリポジトリの `.venv/bin/python` があれば優先し、なければ `python3` を使います。`PYTHON=...` で明示指定も可能です。今回確認した既存環境はPython 3.13.15、SDKは `google-genai==2.20.0` です。システムPythonにはSDKがなく、仮想環境を使わない実行で `No module named 'google'` が発生していました。

SDKは [公式のgoogle-genai](https://googleapis.github.io/python-genai/) を `requirements-gemini.txt` にバージョン固定しました。uvが利用できる環境では `make setup-gemini` で未作成の仮想環境を作り、指定SDKを導入できます。既存仮想環境は作り直しません。pipを利用する場合は `python3 -m venv .venv` で新規環境を作成してから `.venv/bin/python -m pip install -r requirements-gemini.txt` を実行できます。SDKとHTTPX/HTTPCoreの版を固定しています。その他の推移依存はSDKの指定範囲で解決され、実行時の主要バージョンはruntime auditに保存します。

`make check-sdk` は実SDKの `from google import genai` だけをネットワーク遮断下で確認し、Clientの生成もAPI呼び出しもしません。`make check` は実SDKをHTTPモックへ接続する4件の無料テストも必須にします。外部ネットワークは遮断し、合成キーだけを使用します。依存関係の構築・import確認はprobe実行の許可を意味しません。

### choice-ID監査（追加API不要の整備）

共通Gatewayの各 `call_audit` レコードに `model_response`（宣言済みの最終回答JSON）、`choice_response`（元のchoice_id・amount・reason）、`materialized_action`（復元action）、`validation_status` を保存します。`run_id / run / turn / agent_id / attempt / call_id` でtransport監査と対応します。reasonは公開の行動理由であり、SDKの内部推論・thought・署名・生のresponseオブジェクトは取得・保存しません。認証値は環境内の秘密値と既知の秘密フィールドを除去し、回答に認証値が混入した場合は検証失敗とします。

probeでは `decision.audit.json` に送信前・回答取得後・検証後を永続保存します。1TURN/8TURNでも同じレコードをcheckpointと最終resultへ保存します。監査書込失敗は即停止し、API再試行しません。researchの入場検証は元のchoice-IDによる再復元、構造化回答との一致、transportとの対応を必須にします。過去ログはそのまま保持し、欠けた元回答を推測で補完しません。

### ChatGPTがGitHubから結果を直接確認する

入口は [CHATGPT_HANDOFF.md](CHATGPT_HANDOFF.md) と [results/status/latest.json](results/status/latest.json)。公開済みの最新probe／turn／experiment／正式研究／失敗runを索引から確認できます。公開JSONはAgentの最終判断・choice-ID・復元action・監査・実際に完了したTURNの世界状態を含みます。秘密情報や壊れた監査のあるrunはログを公開せず、拒否コードだけを記録します。

`make publish-status` は原本の検証・secret scan・公開ファイルの準備のみで、APIやpushは行いません。実験終了後も同じ準備処理を自動実行します。`make sync-status` で無料検証後、観測ファイルだけを現在branchへcommit/pushできます（main/master禁止）。この同期後は、写真ではなく「終わった」「確認して」と伝えればChatGPTがGitHubから確認できます。未同期のローカル結果はGitHubから見えません。

原本runとcheckpointはGit管理から除外し、既存の追跡済み研究結果は保持します。`git config --local core.hooksPath .githooks` でpush対象コミットそのものの検証を有効にできます。CIも公開ファイルを検証します。研究状態の冒頭はmachine stateから生成し、以前の研究記録はその下に保持します。

### 実験終了時のremote観測

明示許可された実験は、終了後にsanitized観測の生成・検証・commit・作業branchへのpush・fetch後のHEAD照合まで自動実施します。完了表示は `REMOTE OBSERVABILITY READY: <commit>`。同期失敗時は実験を繰り返さず `make sync-status` のみ再実行してください。[仕様・停止条件](docs/REMOTE_PUBLICATION.md)。

## 正式原則と最初の完全worldline

- [Design / Research Principles](DESIGN_RESEARCH_PRINCIPLES.md): 技術・研究・UI/UX・社会実装の判断基準。
- [最初の完全8TURN解析](docs/research/20260917T075421Z-11147417-analysis.md) / [全TURN資料](docs/research/20260917T075421Z-11147417-turns.md) / [machine timeline](results/status/analyses/20260917T075421Z-11147417/timeline.json)。
- [原則の現状評価とvisual primitives](docs/CREATIVE_RESEARCH_ROADMAP.md)。新方式の単一worldlineであり、以下の既存16条件研究とは別系列。
