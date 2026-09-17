# V3 第6段階 — 観測・研究記録接続・世界線証拠モデル

主質問「世界の安定化は、国家の自律性や資源分布とどのように両立・衝突するか」、副質問A「条件付き協力は有限資源不足をどこまで吸収できるか」、副質問B「資源依存構造は局所障害の波及と回復経路をどう変えるか」に必要な測定層。問いに対する結論や世界の採点を実装しない。

`測定値 ≠ 価値判断 ≠ 研究上の解釈`、`OBSERVATION ≠ CONTROL`。

## 構成と範囲

- `homeostasis_v3/metric_definitions.py`: 18指標族のmachine-readable定義台帳。metric_id、definition、inputs、calculation、unit、aggregation、known_limits、introduced_version。定義全体と個別定義のdigest。
- `homeostasis_v3/observation.py`: `OBSERVATION_SCHEMA`、純粋な `observe`、証拠検証・完全再計算、比較条件、別artifactの解釈、Evaluator用immutable JSON view。
- `homeostasis_v3/observation_registry.py`: 将来のRegistryレビュー用pending evidence契約。Registry登録・allowlist承認・公開は行わない。
- `tests/v3/test_observation.py`: 第5段階の合成checkpointに対する無料テスト。

第1〜5段階の世界法則、決済、TURN実行器、初期値、既存JSON、Registry、V1/V2、UIを変更しない。正式Simulation・正式Agent・第7段階は実行しない。

## 測定時点・分類・証拠

TURN_CLOSEで確定した検証済みcheckpointのみ受理する。genesisや途中snapshotから観測記録を作らない。国別・世界別の不足などTURN中のflowは、完了checkpointが保存した正式ledgerから読む。在庫などstockはTURN末状態から読む。Coordinatorの文章や意図から世界指標を推定しない。

各recordはschema version、provisional reference、worldline ID、TURN、checkpoint digest、world input digest、測定phase、metric定義digestを持つ。各metric cellは定義ID・定義digest・status・value・unit・evidenceを持つ。evidenceはcheckpoint digest＋JSON pointer＋参照値digest。国家・資源・経路・Choiceの識別を保ち、原本のledger、network、settlement、Choice、eventまで参照できる。

`validate_observation` はschema、digest、phase、分類、証拠参照を検証。`verify_observation` は全指標を原本から再計算して完全一致を要求し、編集した値にhashだけ付け直したものも拒否する。

artifact_class契約には `test_fixture / validation_run / formal_experiment` を識別可能にする。現在のTURN checkpointは `v3_offline_turn_checkpoint` なので、このadapterは前二者のみ生成し、formal_experimentを拒否する。experiment_id=null、research_eligible=false、publication_status=withheld。正式runnerと承認済みprovenance gateなしにfixtureを正式研究へ昇格できない。

## 指標の意味

| 指標族 | 測定内容と限界 |
|---|---|
| 恒常性構成要素 | 資源ごとの必須需要・実充足・不足・充足率。国家別の明示参照状態からの残高差、回復過程を別々に保持。世界善悪スコアは作らない。 |
| 回復力 | 国家/資源ごとの初回不足、最大・累積不足、最初の連続TURN間不足減少、不足後に初めて0へ到達したTURNと所要TURN。復旧機構による効果とは主張しない。 |
| 国家自律性 | 選択数、条件付き選択、提出Choiceの個別可能数、catalogue候補数、明示拒否、適用制度の同意要件、提案の有無、主体境界。候補数を自律性スコアにしない。未選択候補の可能性、実世界の強制や動機は不明。 |
| 国家的自立性 | 国内残高、必須需要、生産能力、需要超過備蓄、備蓄のみの継続可能TURN、当TURN外部着荷、実供給元数、潜在供給元・経路。備蓄期間は需要固定・生産/損失/外部供給なしの条件付き算術値。 |
| 資源偏在 | 国別残高・需要・不足の分布と、国内/pool/輸送中/生産中の世界総量を分離。食料とエネルギーの量を合算しない。 |
| 能力低下 | capacity別の稼働量と最大稼働量との差。単位を保持し、被害原因は推定しない。 |
| 供給網 | 資源に対応し、利用可能で、経路・共有容量・発送国輸送能力が最低1単位を通せる有向単純経路。複数段階到達と代替経路を保持。ただし同意・在庫・未来の着荷可能性を証明しない。 |
| 依存集中 | 供給元・経路・共有容量群別の構造的経路数と実着荷量を別々に測る。各重みとHHI（share二乗和）を保持。空集合はnot_applicable。脆弱・悪いとは判定しない。 |
| 負荷 | route/shared groupの当TURN発送量×輸送換算、容量、使用率、資源別内訳・輸送中量。資源ごとのcapacity表記は同じ共有分母であり独立容量ではない。待機queue未実装なので待機量unknown。 |
| 取引 | 当TURNの要求・個別可能・成立・発送・到着済み量、全量/部分/不成立、reason code件数。過去発送の当TURN着荷は別のreceipt一覧に保持。高成立率を善としない。 |
| 波及 | 明示外乱のoriginから輸送/生産投入の構造的依存経路を追跡。連続checkpointの不足増加が経路上にある場合だけ観測変化を併記。時間順序は因果同定ではない。 |
| 紛争負荷 | V3定義なしのunknown。拒否を紛争へ変換しない。 |
| 過剰/過少反応 | 参照政策と必要反応量が未定義なのでnot_measured。V1概念を流用しない。 |

自立性の生産能力はresource unit / TURNであり、在庫と異なる量。潜在供給元は複数段階を含む構造的到達可能性。代替供給元数は候補数から1を引いた追加選択肢数で、現在の供給元を特定した反実仮想ではない。poolは観測された勘定上の供給元であり、元の生産国を捏造しない。

## 時系列・不明値

累積・最大・初回時点等を全期間値として出すにはTURN1から現在までの連続checkpointを必要とする。各checkpointのcontext、config、履歴prefix、隣接TURNの期首digestを照合する。履歴欠落時に0埋め・補間しない。明示参照checkpointがない残高逸脱もunknown。

statusは `measured / unknown / not_applicable / not_measured`。測定結果0と不明値nullを区別する。需要0の充足率や空集合HHIはnot_applicable。観測期間内に不足減少/解消がない場合は「未観測」であり、将来の回復不能とはしない。復旧則は第5段階のまま未定義。

世界集計と国別値を常に同時保存する。世界の不足減少と特定国の不足増加が共存するfixtureで、局所の変化が失われないことを検証する。これを自動的に不公平・失敗へ分類しない。

## 波及の証拠強度

`origin / affected_state / resource / first_affected_turn / dependency_path / effect_type / evidence_strength / causal_claim` を保持。

- `structurally_possible`: TURN末の依存構造上で接続している。停止経路も構造として残し、その時点のavailabilityを併記する。
- `change_along_dependency_path`: 外乱以後、隣接checkpointで不足増加が観測された。first_affected_turnはこの**最初に観測できた増加TURN**で、潜在的な物理的発生時点の推定ではない。
- `unknown`: 例えば復旧capacity低下は、資源への作用則未定義なので架空の資源波及経路を作らない。

全てcausal_claim=false。BFSで代表的な最短構造経路を一つ保存し、全因果経路の列挙とはしない。到達可能性の単純経路列挙は既定10,000件まで、超過時は観測技術失敗とし結果を切り捨てない。制限値もprovenanceへ記録する。

## 解釈・Evaluator・比較

`interpretation` は観測digestと証拠pointerを参照する独立artifact。kindはinterpretation/commentary/value_judgment。測定値やcheckpointを更新しない。Evaluatorにはimmutable JSON viewを渡し、改変したcopyは原本へ戻らない。成功/失敗分類や次イベント生成は実装しない。

比較は同じschema・metric定義digest・測定phase・artifact_classを要求する。互換性だけで同じ実験条件・因果比較とは主張しない。初期状態、Policy、外乱、履歴範囲、参照状態は別途確認する。既存config hashにはcontext IDも含まれるため、異なる世界線のconfig hash不一致だけで物理則が違うとは断定しない。

## Registry接続とPUBLIC境界

既存RegistryはV1/V2/sharedの承認済みartifactだけを受理している。第6段階では既存schema・registry.json・allowlistを変更しない。

`pending_evidence` はV3観測を再計算検証し、secret pattern scanと相対JSON path検証後に、既存の `{path, pointer}` 形式の参照候補を生成する。canonical SHA256と観測digest、checkpoint、metric定義digestを持つが、`not_registered / withheld / source_eligible=false` のまま。

将来接続時にはV3 schema対応、実在tracked非symlinkファイル、正確な**ファイルbyte hash**のallowlist承認、source分類とprovenance、独立した公開承認が必要。canonical hashをファイルbyte hashと混同しない。候補生成はファイル存在・登録・公開を意味しない。REGISTERED ≠ PUBLICを維持する。

今回のfixture観測はテストの一時領域内だけで生成・再読込検証し、正式研究artifactとしてGit保存しない。科学的発見は主張しない。
