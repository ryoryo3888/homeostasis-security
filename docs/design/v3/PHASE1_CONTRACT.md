# V3 第1段階：データ契約・識別・創発余白

2026-09-18。ユーザー承認により第1段階のみ実装。以前の設計文書の「研究質問選択待ち」は本承認で更新する。第2段階以降は未着手。

主質問：**世界の安定化は、国家の自律性や資源分布とどのように両立・衝突するか？**
副質問A：独立した国家の条件付き協力は、有限資源の不足をどこまで吸収できるか？
副質問B：資源依存の構造は、局所障害の波及と回復経路をどう変えるか？

## 実装範囲

`homeostasis_v3/contracts.py` はJSON Schemaを使う純粋validator。import時のI/O、SDK、Agent、runner、決済器、UI、指標計算はない。新規Experimentのversionは厳密にv3、schemaは1。旧データを変換・再ラベルしない。Registryのv3拒否も維持する。

国別stock口座とcapacityを別型で表現する。口座は所有者・場所・資源・単位・残高・輸送中フラグを持つ。同じ口座を二重計上できない。生成・消費・損失・移転は別カテゴリの台帳entryで、移転は1entryのsource/targetにより両脚を表す。capacityはproduction/transport/recoveryに分離し、残高とは異なるunitを参照する。

dependencyは供給国・需要国・資源・route・capacity・alternative routes・upstreamを参照する。存在しない参照、自己依存、繋がらない多段参照を拒否する。複数国家の合法な循環は拒否しない。国数8を型の上限にしない。

## 法則と結末の境界

**世界の法則は設計する。世界の結末は設計しない。**

- intentはproposal_id=nullを許す。国家がCoordinator応答だけへ閉じない。
- law_refとchoice_refは明示的なID/hash registryへ照合する。行動名の永久固定enumは設けない。将来の候補生成器が許可法則から作ったcatalogueを参照する。未知の自由tupleは通さない。
- intent / feasibility / settlement / state_changeは別schema。回答から状態patchを直接渡せない。全体検証入口はvalidate_pipeline。hashで同じsnapshotと各段階を結び、成立していない意図による状態変化を拒否する。
- Coordinatorのmessageはobservation/proposal/coordination_proposalだけ。命令・強制採択・直接移転・回復目標fieldを持たない。
- event_inputは現在のworld、行動、残高、不足、負荷、取引／TURN履歴と規則のhashを参照する。予定TURN別結末や回復予定を受け付けない。event生成器自体は未実装。
- PolicyはID/hashで交換可能。必要需要先行予約、同意、期首pool、最低充足率優先は承認された将来の基準制度。今回はそのアルゴリズムを実装せず、世界型へハードコードしない。

## 自律性と自立性

national_autonomyは自己決定権・委任・選択の証拠。national_self_relianceは外部供給／経路喪失の仮定セットと必須機能維持の証拠。型と観測軸を別にし、どちらにも「高いほど良い」という集約目的を与えない。自立性の数値・反実仮想計算は後段で実装する。

## 実験条件固定

FrozenExperiment.freezeは条件をcanonical JSON文字列へコピーしてsha256固定する。外部の元dictを変えても条件は変化しない。verifyは研究質問、制度、初期条件、endpoint、反復数、seed、法則、観測軸の変更を拒否する。

重要：信頼された保存層が初回digestを保持する必要がある。候補とanchorを両方差し替える攻撃への認証機構ではない。正式登録・durableなanchor保存・既存ID再利用拒否はRegistry接続段階の責務。今回正式Experimentを登録していない。

## 保証範囲と後段の責務

これはデータ境界の強制であってsandboxや暗号署名認証ではない。authorized_producerは将来の信頼されたcoreが渡す値であり、Agent入力からコピーしてはいけない。consent/evidence/validatorのhash参照について、実在証拠の検証・権限認証・物理的feasibility・全体保存則の証明は後段で必要。validate_change_accountsは開始残高を越える集約支出を検出するが、完全な決済を実行しない。

規則や初期条件のhashだけでは、その中身に脚本がないことまでは証明しない。将来rule実装・scenarioのレビューと故障注入テストで固定結末への依存を検証する。本段階には回復関数・危機スケジュール・協力誘導・worldline生成処理そのものがない。

free test runnerにV3契約試験を追加。既存engine、UI、研究結果、Registry、layout/copy Baselineは変更しない。V1/V2の公開資産byte一致と既存layout試験を維持する。
