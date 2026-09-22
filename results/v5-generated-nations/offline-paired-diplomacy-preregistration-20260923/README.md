# V5 オフライン派生比較 preregistration

このpreregistrationは、既存36ターン観測から外交通信あり／なしを派生比較するためのものです。APIは実行しません。新しいLeader判断も生成しません。

## 旧計画との関係

既存の `10 seed × A/B = 20 run` preregistration は、Gemini本実験として新規runを行う計画でした。これは削除せず、旧計画・未実行として保存します。

このオフライン版では、既存36ターン観測を唯一の入力として、外交通信を残した場合と、同じ記録から他国宛の通信・提案を取り除いた場合を比較します。

## 固定条件

- TURN 1〜36
- Leader判断 432件
- 既存国家・既存Leader・既存危機内容
- 既存物理成立条件
- API未使用

## 主な読み方

この比較は、36ターン版で観測された関係網が、外交通信という通路にどの程度依存して見えていたかを確認する制約除去観測です。

## 出力

- `results/v5-generated-nations/offline-paired-diplomacy-derived-20260922/offline_paired_diplomacy_summary.json`
- `results/v5-generated-nations/offline-paired-diplomacy-derived-20260922/offline_paired_diplomacy_summary.md`
