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
