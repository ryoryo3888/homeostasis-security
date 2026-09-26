# HOMEOSTASIS SECURITY

AI Agentが状況を受け取り、何を話し、何を選び、その後に何が起きるかを観測するプロジェクトです。
現在の入口と、過去の実装・実験記録を以下に整理しています。
未使用の画面・Pythonの控えと確認済みの重複・中間物など46件は[保管フォルダ](archive/README.md)にまとめています。

## 現在の公開版

| 版 | 画面 | 記録の位置づけ |
| --- | --- | --- |
| V1：二国間の恒常性 | [開く](https://ryoryo3888.github.io/homeostasis-security/dashboard_v1.html) | 16条件・36 runの保存済み結果。代表runはこの36 runに含まれる |
| V2：地球規模の恒常性 | [開く](https://ryoryo3888.github.io/homeostasis-security/dashboard_v2.html) | 独立シナリオの保存済み1 run・5ターン |
| V3：自由対話 | [開く](https://ryoryo3888.github.io/homeostasis-security/results/v2-five-runs/index.html) | 5回・各8ターンの保存済み対話。発言だけから資源変化を算出しない |
| V4：相互依存 | [開く](https://ryoryo3888.github.io/homeostasis-security/dashboard_v4.html) | 開発中の有限資源モデル。画面の検証データと実LLMの観測記録は別に扱う |

公開名と内部ファイル名の数字は一部異なります。旧V3の実装は現在のV4です。
`dashboard_v3.html`もV4への互換入口として残しています。
[番号整理の記録](docs/architecture/VERSION_NUMBERING_REVISION.md)で対応を確認できます。

## V6研究論文

ユーザーの明示目的に反してAIが変更した研究と作品（v1.12／2026年9月26日／全20ページ）

- [Webで読む](https://ryoryo3888.github.io/homeostasis-security/docs/papers/homeostasis-security-v6-paper-v1.12.html)
- [Markdown全文](https://ryoryo3888.github.io/homeostasis-security/docs/papers/homeostasis-security-v6-paper-v1.12.md)
- [PDF固定版](https://ryoryo3888.github.io/homeostasis-security/docs/papers/homeostasis-security-v6-paper-v1.12.pdf)

## 作業と資料の入口

| 目的 | 入口 |
| --- | --- |
| 現行コード・保存データ・旧資料の場所を探す | [リポジトリ案内と保管一覧](docs/REPOSITORY_MAP.md) |
| 未登録JSON16件の扱いと保管理由を確認する | [追加調査](docs/UNREGISTERED_JSON_AUDIT.md) |
| Agentの自由、人が決めた条件、測定の限界を確認する | [観測の透明化](docs/architecture/OBSERVATION_TRANSPARENCY.md) |
| ローカルLLMの小規模試行を準備する | [V4 Local pilot](docs/architecture/LOCAL_PILOT.md) |
| run条件・失敗・RAW / DERIVEDの保存方法を確認する | [Evidence Format](docs/architecture/EVIDENCE_FORMAT_V1.md) |
| 既存V1・V2の保存結果を照合する | [実験台帳](research/experiments/README.md) |
| 公開画面の変更範囲・検証手順を確認する | [Visual Constitution](docs/architecture/HOMEOSTASIS_VISUAL_CONSTITUTION.md) / [Layout Contract](docs/architecture/LAYOUT_CONTRACT.md) |

現在の工程は、透明化・証拠形式の準備 → ローカルLLMで小規模試行 →
実測を確認して観測数を増やす → 生ログ公開 → 横断解析・追加検証です。
最終的な研究文書は観測後にまとめます。技術的な失敗も記録し、観測数へ成功例だけを選びません。

V1・V2は保存済み結果の閲覧を維持しています。`simulation_v2.py`による新規世界更新は、
未承認のルールを補わないため停止しています。現在の自由対話の入口はV3・V4です。
V2の初期事件は独立シナリオであり、V1の実行結果を引き継いだものではありません。

## 保存済み画面を見る

追加API通信なしで、ローカルでも公開画面を閲覧できます。

```bash
python3 -m http.server 8000
```

リポジトリ直下で起動し、<http://localhost:8000/dashboard_v1.html>を開きます。
終了は`Ctrl+C`です。実験の再実行とは別の操作です。

## 過去の説明を保管

下記は整理前のREADMEを原文のまま保管したものです。
旧名称の「最終版」「V3」、旧実行手順、V1からV2への接続説明には、その後の修復・番号整理と
一致しない記述があります。現在の入口と状態には上記の案内を使用してください。
保存時の説明を消さずに検証できるよう、原文と参照先を同じ場所に残しています。

<details>
<summary>旧README全文（履歴資料・現在の実行手順ではありません）</summary>

<!-- HOMEOSTASIS_RETAINED_README_BEGIN -->
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

## Visual Constitution / Layout Contract

完成済みV1/V2の構造は [Visual Constitution](docs/architecture/HOMEOSTASIS_VISUAL_CONSTITUTION.md)
で固定しています。新しい研究表示は [Content Slot Contract](docs/architecture/CONTENT_SLOT_CONTRACT.md)
を使用し、Earthや操作領域を移動して場所を作らないでください。
[Layout Contract](docs/architecture/LAYOUT_CONTRACT.md) の `make check` で無料検証します。
V3は多国間・資源ネットワークの研究方向です。この基盤追加はV3 UI開発の開始ではありません。

## 現在のバージョン名（2026-09-20）

- [V1：二国間の恒常性](dashboard_v1.html)
- [V2：地球規模の恒常性](dashboard_v2.html)
- [V3：自由対話](results/v2-five-runs/index.html) — 5回・各8ターンの保存済み観測記録
- [V4：相互依存（制作中）](dashboard_v4.html) — これまでV3と呼んでいた多国間・有限資源モデル

上記以前の説明・設計資料にある多国間モデルの「V3」は現在のV4です。実験結果・内部識別子・旧URLは保持しています。[番号整理の範囲](docs/architecture/VERSION_NUMBERING_REVISION.md)。
<!-- HOMEOSTASIS_RETAINED_README_END -->

</details>
