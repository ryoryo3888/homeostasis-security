# V3 第5段階 — TURN実行器・主体境界・監査・checkpoint

第4段階 `ed819ba8588ad0f1c40c03cdb53af0afb316e8e0` を接続する。世界の法則を定義し、世界の結末を予定しない。対象はオフライン世界法則の統合検証であり、正式Experiment、研究上の発見、8TURN世界線ではない。

## 構成

- `homeostasis_v3/turn.py`: 一回の `TurnRunner.run`、読み取り専用JSON snapshot、国別入力、明示外乱、生産投入、監査、入力replay。
- `homeostasis_v3/checkpoint.py`: 検証済みcheckpoint記録とatomic HEAD採用。
- `homeostasis_v3/settlement.py`: 新規engineへのtrusted core専用履歴復元入口だけ追加。Phase 4のchoice/同意/配分/決済則は維持。
- `tests/v3/test_turn.py`: 合成fixtureによる検証。`tools/run_free_tests.py` / `make check` の既存discovery対象。

既存baseline/networkファイル、V1/V2、公開UI、既存Simulation Engine、研究原本、Registryは変更しない。第6段階、Agent、イベント生成AI、V3 UIへ進まない。

## 正式な段階と順序

`PHASES` に以下を機械的に定義し、各段階のevidence hashを保存する。

1. TURN_OPEN — 最後の検証済みcheckpointと設定digest照合。
2. ARRIVAL — 予定TURNへ達した輸送・生産中勘定を在庫へ振替。一度だけ受取。
3. SHOCK — 明示された資源損失、能力低下、経路停止、需要変更。
4. OBSERVATION_FREEZE — 全国家共通のimmutable JSON snapshotを固定。
5. COORDINATOR_INPUT — 任意の公開提案。省略可。
6. CHOICE_COLLECTION — 全国家のID選択・数量・公開理由を収集。不作為は空リスト。
7. CHOICE_VALIDATION — Python catalogueからmaterialize、国家identity、同意を検証。
8. FEASIBILITY — 個別物理制約。
9. JOINT_SETTLEMENT — 同一候補集合の条件・共有容量・在庫競合。
10. ATOMIC_APPLY — 第4段階の原子的決済をTURN私有コピーへ適用。
11. TRANSIT_UPDATE — 発送・所有権・着荷予定を記録。
12. CONSUMPTION — 必須需要に対し実在庫からのみ消費。不足を記録。
13. PRODUCTION — 消費後の同一在庫から投入、生産能力・batch・遅延を適用。
14. RECOVERY — `NO_DEFINED_RECOVERY_LAW`。状態変化なし。
15. CONSERVATION — 損失・消費・生産投入/出力を含む収支検証。
16. TURN_CLOSE — 正式な末状態候補を一度確定。
17. EVALUATION_SNAPSHOT — 末状態と同じworld hash、同じ内容。
18. NEXT_EVENT_INPUT — 同じ末状態、不足、能力、ネットワーク負荷、未解決条件、全履歴。
19. AUDIT — 入出力digestと段階証拠。
20. CHECKPOINT — 検証済み候補の生成。永続的採用は下記storeで行う。

個別可能性・共同成立・原子適用は既存settle呼出しの内部で順に実行する。一連の成功後に実際のauditを段階別に抽出する。呼出し内部で失敗した場合、存在しない途中commitを主張せず、technical failureに `SETTLEMENT_TRANSACTION` と三段階のspanを保存する。

順序は依頼の基本順を維持。消費→生産は第2段階の「当期生産は期首消費を賄わない」を維持するため。先に着荷、後に外乱なので、着荷済み在庫もそのTURNの明示損失対象になり得る。生産投入の循環を処理順で解決しないため、生産物のcreditは全投入debit後に行う。

## 主体境界

国別 `CountryInput.choose` は共通snapshotと任意の提案を受け、choice ID/量/公開理由だけ返す。実行tupleはtrusted Python catalogueが所有する。Coordinator回答に限定するfieldはない。他国への自発取引・支援・拒否・不作為は提案なしでも入力できる。備蓄は不作為で可能。未知の新行動は第4段階の契約拡張を要し、自由文から実行しない。

提案入力は `proposal_id / public_reason` の最小契約。国家Choice・同意・world patchを受け付けない。将来、構造化提案を追加する場合も権限境界を維持する。

同意は別の国別callbackへ全Choiceの読み取り専用snapshotを渡して収集し、各国が自身の同意だけを返す。pool権限は別の明示入力。全選択・同意を揃えてから一括決済する。国家の処理順はIDで正規化し、国別snapshotを更新しない。

`Snapshot` はimmutableなJSON文字列を保持し、readはprivate copyを返す。Authority、core capability、署名鍵をcallbackへ渡さない。callback自体はtrusted Python adapterであり、同一プロセス内の任意コード攻撃者を隔離するsandboxではない。将来のモデルにはJSON境界だけを公開する。

Evaluator入力は受け付けない。評価用snapshotは末状態のcopyであり、出力によって決済を変更する経路はない。

## 物理則と収支

外乱はevent ID・型・対象・資源・量・証拠を持ち、未知参照/範囲外量は技術失敗。異なる外乱はevent ID順で適用し、その順序を監査する。同一対象への複数需要変更は後のIDの値になるため、入力作成者は競合する代入を避ける必要がある。固定TURN番号や特定国家の役割は実装しない。

消費は `min(実在庫, 必須需要)`。未充足需要は消費に計上しない。

生産は第2段階の能力上限と第3段階の必須投入比率を使用する。複数投入があるときはoutput batchの最小公倍数の単位で生産する。共有する国/投入資源ごとに、全希望投入量に対する実在庫の比率を求め、各生産はその必須投入比率の最小値で比例縮小し、batch単位で切り下げる。これは明示した `RULES` の参照物理配分則であり、最大生産・回復最適化ではない。丸め後の余りを他生産へ自動再配分しない。依存のない生産は能力由来の外生生産を維持する。

投入はそのTURNに消費する。依存付き出力は `production_pending` に保持し、最大のoutput_delay後に着荷する。出力量は生成時点で生産中勘定へ計上、在庫への振替時には再生産として数えない。依存なし出力はTURN末在庫へ入る。同じ生産段階内の出力を別生産の投入に使わない。

資源ごとに次を検証する。異種資源の単位を合算して保存を主張しない。

`末総量 = 期首総量 − 外乱損失 − 必須消費 − 生産投入 + 生産出力`

総量は国内在庫、pool、未着荷輸送、生産中を含む。資源変換・外生生産があるため「各資源の総量が不変」とはしない。

輸送capacityは発送TURNのthroughput。輸送中であることによる翌TURN以降の経路占有は第3〜4段階で未定義のため追加しない。復旧も資源費用・対象・効果の法則が未定義なので、capacityの存在だけで回復を発生させない。

## 永続化・採用条件

`run` は私有コピーで最後まで検証した候補を返す。例外が起きたら候補を返さず、入力checkpointを変更しない。候補がメモリ上にあるだけでは、durable storeのHEADは進まない。

`CheckpointStore.save(candidate, expected_digest=...)` はローカルPOSIX filesystem上で以下を行う。

1. 候補をJSONへ独立コピーし、schema相当の不変条件・各digest・phase順序・snapshot一致を検証。
2. flockで書込みを直列化し、現在HEADとexpected digestを比較。
3. genesisまたは一つ先のTURN、同一context/config、期首参照の連続性を確認。
4. temporary fileへ書込み、flush/fsync、再読込照合、記録名へatomic rename、directory fsync。
5. commit markerであるHEADをtemporary fileからatomic rename。
6. directory fsyncでHEADの耐久性を確認。

HEADが参照しない記録・temporary fileは正式checkpointではない。HEAD切替前に失敗すればlast valid checkpointはそのまま。HEAD切替後のdirectory fsync失敗は `CommitUncertain` として区別し、HEADを再読込して採用状態を確認するまで再実行しない。既に採用されたTURNを自動再試行しない。

正常なfilesystem上のプロセス中断・write失敗に対する境界であり、分散transaction、ネットワークfilesystem、悪意あるファイル置換、ディスク自体の故障、全環境の電源断耐久性を保証しない。checksumは改変検出であって署名認証ではない。保存directoryはtrusted hostが管理する。秘密鍵は永続化しない。

## 再現・監査・失敗

input digestは期首checkpoint、正規化外乱、catalogue、国家選択、同意、提案、Policy/法則/設定を含む。output digestは末world state。checkpoint digestは入力・出力・監査・履歴全体を覆う。`replay` は保存入力から元callbackを呼ばずに同一末状態・同一監査を再生成する。

技術失敗は `TurnFailure.record` にcode、phase/span、例外型、last valid checkpoint、completed=falseを記録可能。任意の例外メッセージやSDK objectは保存しない。全取引不成立・不足拡大・経路停止は合法な世界結果としてcheckpointへ採用できる。

next-event inputは末world state、不足、能力低下、ネットワーク使用量、未解決条件、過去イベント・Choice・取引の履歴。物語や予定シナリオを生成しない。今後の閉ループ接続点だけを用意する。

## 既知の限界と次工程への境界

第4段階の200,000組の厳密探索上限を維持。探索超過は技術失敗であり、無取引という世界結果へ変換しない。永続署名・Agent adapter・実験runner・registry正式登録・復旧法則・Event AIは未実装。今回の合成fixtureから研究上の法則や成功世界線を主張しない。
