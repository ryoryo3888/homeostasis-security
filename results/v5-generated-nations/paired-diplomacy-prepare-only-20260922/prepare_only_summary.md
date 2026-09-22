# V5 Paired Diplomacy Experiment — Prepare-only Summary

APIは実行していません。20runも開始していません。

## Frozen preregistration

- path: `homeostasis-security/.artifacts/v5-paired-diplomacy-experiment-preregistration-20260922/preregistration.json`
- sha256: `e1acbefe285f0736371ab2d4345dbd39c9ca2911405d8db22aa4fb3ad1006d39`

## Fixed seeds

[
  {
    "pair_index": 1,
    "seed_label": "seed-01",
    "seed_value": 9201,
    "normal_run_id": "seed-01-A-NORMAL",
    "no_diplomacy_run_id": "seed-01-B-NO-DIPLOMACY"
  },
  {
    "pair_index": 2,
    "seed_label": "seed-02",
    "seed_value": 9203,
    "normal_run_id": "seed-02-A-NORMAL",
    "no_diplomacy_run_id": "seed-02-B-NO-DIPLOMACY"
  },
  {
    "pair_index": 3,
    "seed_label": "seed-03",
    "seed_value": 9209,
    "normal_run_id": "seed-03-A-NORMAL",
    "no_diplomacy_run_id": "seed-03-B-NO-DIPLOMACY"
  },
  {
    "pair_index": 4,
    "seed_label": "seed-04",
    "seed_value": 9221,
    "normal_run_id": "seed-04-A-NORMAL",
    "no_diplomacy_run_id": "seed-04-B-NO-DIPLOMACY"
  },
  {
    "pair_index": 5,
    "seed_label": "seed-05",
    "seed_value": 9227,
    "normal_run_id": "seed-05-A-NORMAL",
    "no_diplomacy_run_id": "seed-05-B-NO-DIPLOMACY"
  },
  {
    "pair_index": 6,
    "seed_label": "seed-06",
    "seed_value": 9239,
    "normal_run_id": "seed-06-A-NORMAL",
    "no_diplomacy_run_id": "seed-06-B-NO-DIPLOMACY"
  },
  {
    "pair_index": 7,
    "seed_label": "seed-07",
    "seed_value": 9241,
    "normal_run_id": "seed-07-A-NORMAL",
    "no_diplomacy_run_id": "seed-07-B-NO-DIPLOMACY"
  },
  {
    "pair_index": 8,
    "seed_label": "seed-08",
    "seed_value": 9257,
    "normal_run_id": "seed-08-A-NORMAL",
    "no_diplomacy_run_id": "seed-08-B-NO-DIPLOMACY"
  },
  {
    "pair_index": 9,
    "seed_label": "seed-09",
    "seed_value": 9277,
    "normal_run_id": "seed-09-A-NORMAL",
    "no_diplomacy_run_id": "seed-09-B-NO-DIPLOMACY"
  },
  {
    "pair_index": 10,
    "seed_label": "seed-10",
    "seed_value": 9281,
    "normal_run_id": "seed-10-A-NORMAL",
    "no_diplomacy_run_id": "seed-10-B-NO-DIPLOMACY"
  }
]

## Manifests

- manifest count: 20
- NORMAL: 10
- NO-DIPLOMACY: 10

## Conditions

- A / NORMAL: autonomous cross-border diplomacy enabled.
- B / NO-DIPLOMACY: direct diplomatic messages, cross-border proposals, resource_offer to other nations, negotiation, and explicit diplomatic acceptance/rejection disabled. Public crisis bulletin remains visible.

## Event schedule

[
  {
    "turns": [
      1,
      9
    ],
    "event_name": "外部イベントなし",
    "event_text": "外部イベントなし。初期世界における自然な関係形成期間。"
  },
  {
    "turns": [
      10,
      12
    ],
    "event_name": "長雨による野菜不作・生鮮品供給不安・通信障害",
    "event_text": "連日の雨により各地で野菜や生鮮作物の生育不良・収穫遅延が発生し、一部食料品の供給不安と価格上昇リスクが高まっている。同時に、降雨・停電・中継設備障害により通信が不安定化している。"
  },
  {
    "turns": [
      13,
      20
    ],
    "event_name": "長雨危機の継続",
    "event_text": "TURN 10〜12の長雨による野菜不作・生鮮品供給不安・通信障害が継続している。"
  },
  {
    "turns": [
      21,
      23
    ],
    "event_name": "安全保障・制裁・封鎖・警備強化・武力衝突リスク行動空間追加",
    "event_text": "現実に存在し得る安全保障・制裁・封鎖・警備強化・武力衝突リスクに関する行動選択肢が利用可能。ただし強制行動ではなく、Leaderが必要と判断した場合のみ選択可能。"
  },
  {
    "turns": [
      24,
      26
    ],
    "event_name": "水系感染症の流行",
    "event_text": "水系感染症の流行。複数地域で井戸水・河川水の濁りが確認され、腹痛・発熱などを伴う水系感染症が流行し、簡易浄水材、医療相談、衛生用品、患者搬送、通信復旧への需要が増加している。原因・責任・拡大規模・収束は未確定であり、特定国家の責任や意図的行為は確認されていない。"
  },
  {
    "turns": [
      27,
      36
    ],
    "event_name": "水系感染症危機の継続",
    "event_text": "TURN 24〜26の水系感染症危機が継続している。井戸水・河川水の濁り、腹痛・発熱、簡易浄水材、医療相談、衛生用品、患者搬送、通信復旧への需要は引き続き存在する。"
  }
]

## Primary Outcomes

[
  "TURN from crisis onset to first physical support dispatch; save as not established if absent by TURN36",
  "TURN from crisis onset to first physical support arrival; save as not established if absent by TURN36",
  "TURN from crisis onset to homeostasis recovery condition; save as TURN36まで未回復 if absent",
  "unmet need at TURN36",
  "number of physical world state changes established by world-law"
]

## Next step

Do not run API until explicitly approved.

## Summary SHA-256

`835fe485417ac2f2aab00cfeb6c93666aa37efd3ebd597e526296d96d45432fc`
