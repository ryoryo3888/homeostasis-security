# V3 第3段階：多段階相互依存の可能性空間

第2段階の国家・資源・生産・消費・収支は無変更。第3段階はnetwork層、静的到達・依存追跡、明示的なオフライン輸送検証を追加する。

## ファイルと境界

- `homeostasis_v3/network.py`：network schema/validator、候補経路、依存鎖、構成要素取得、offline transit check。
- `scenarios/v3/synthetic_network.json`：第2段階baselineのhashに固定した合成ネットワーク。Registryへ登録しない。
- `tests/v3/test_network.py`：静的構造と検証用輸送の無料テスト。

新しい国家判断、Coordinator、交渉、choice生成、条件付き協力、完全なfeasibility/atomic settlement、配分Policy、閉ループ危機、Evaluator、正式worldline、V3 UIはない。

## 合成初期構造

第2段階の8 stable state_idをノードとして参照。schema/探索に国家数8の固定上限はない。基準ネットワークは18本の有向経路（隣接する環の両方向16本＋2本のcross-link）、共有capacity group 4個、生産投入依存8個。全56方向を結んだ完全graphではなく、全国家間に到達可能性がある。経路の逆向きは自動生成せず別recordで明示する。

経路：route_id/source/destination/resource_types/capacity/delay/availability/shared_capacity_group/provenance。
共有容量：group_id/capacity/unit/provenance。複数資源と複数経路の負荷は同じgroupへ合算する。stock unit→transport unitの明示換算を持ち、初期値はfood/energyとも1:1の合成仮定。物理的に同じ重量だという意味ではない。

個別capacity 6/8/10、共有capacity 16/18/20/22、delay 1/2 TURNは合成値。構造・遅延・共有制約の違いを検証するためで、実物流統計ではない。値・構造の説明は各recordのprovenanceと全体provenanceに保存する。初期availabilityはtrueだが、将来維持・故障・回復の予定は含まない。

双方向環とcross-linkは特定国を救済・破壊するためではなく、複数段と代替可能性を比較するための構成。単一障害点が存在しないことを証明したとは言わない。あるかどうかは後続の構造分析・観測対象であり、故障対象の予約はない。

## 輸送依存と生産投入依存

輸送辺は同じ資源が異なる国家へ届く可能性。
生産依存は同じ国家内のinput resourceがoutput resourceを制約する関係で、輸送辺とは別schema。

基準は全国家のfood productionにenergy 1 unit / food 2 units、output_delay=1を設定。これは合成投入係数で、産業統計でも生産実行でもない。producer、production_capacity、input/output resource・unit、required_input/output_batch、relationship、provenanceを検証する。第2段階の外生生産関数を変更したり、係数を自動適用したりしない。後続で投入依存を実行する際はprotocol versionと入力消費を明示的に接続する必要がある。

静的追跡は `(国家, 資源)` をnodeとし、輸送辺と生産投入辺を別kindで返す。例：MIL energy → RES energy → RES food → FOOD food を追える。これは将来影響が伝わり得る接続であり、不足・生産低下・危機が必ず起きるという予測ではない。停止中の経路も静的影響構造には残し、結果に「potential」を明示する。

不正な同国輸送・同資源自己生産依存は拒否する。複数国の輸送循環や複数資源の長い依存循環は構造として許す。visitedによって探索とtraceは停止し、資源増殖を計算しない。

## 到達・代替・集中

candidate_pathsは有効resource・初期availability・正の容量を持つsimple pathを列挙する。route ID順は出力再現性のためであり優先順位ではない。最短・最良を選ばない。予算limitを超えたら明示エラーで、黙って一部を「全候補」として返さない。

到達可能性は在庫・受取権限・将来の容量・同意・契約成立の保証ではない。候補を表示しても輸送は発生しない。障害を入力したテストでも代替候補を返すだけで、迂回を自動実行しない。

network_componentsは第2段階の国内stock/需要/生産/備蓄構成と、potential direct suppliers / incoming routes / shared groupsを別々に返す。資源不足・依存集中・自立性の単一善悪スコアはない。複数段の代替はcandidate_pathsで別取得する。実取引履歴がないので実際の依存shareやHHIは捏造しない。

## オフライン輸送台帳

正式国家worldではなく、`kind=offline_transport_check` の隔離された検証台帳を使う。呼出し元がshipment ID、route、resource、quantityを全て明示する。これはAgent意図や取引を採択する処理ではない。

dispatch_for_checkは期首国内在庫を減らし、同量をshipmentのin_transitへ移す。arrive_for_checkはdelay経過を検証し、明示された受取時刻に目的国内在庫へ移す。自動到着・自動選択・自動次TURN進行はしない。輸送中shipmentには固定network hashとroute IDがあり、両端と資源・量を追跡できる。所有権譲渡や当事者同意の成立を決定する機能ではない。

輸送capacityはroute、共有group、出発国transport能力を各dispatch TURNで合算する。異種資源を同じ変換単位へ換算して検証する。超過時は全入力を無変更のまま拒否し、部分配分・再予約・最適化しない。受取設備制約・将来予約・法的同意は完全feasibilityを実装する後続段階の責務。

同時刻の到着は期首としてdispatchより先に処理する。再輸送は到着後に明示的な新shipmentが必要で、各辺delay≥1。同TURNで新発送品が連続して瞬間移動しない。

`全国内stock + 未着荷shipment = 開始総量` を資源ごとに検証。生産・消費・損失はこの輸送検証に混ぜない。二重shipment ID、二重受取、負数・0数量、在庫超過、容量超過、早着、時刻逆行、snapshotの差替えを拒否する。内部replayで台帳から在庫を導出し、送信・輸送中・受信を重複計上しない。

台帳は物理整合の証拠であって署名認証ではない。callerが過去recordを丸ごと偽造した場合の真正性は、後続のtrusted runner/監査保存層で確保する。

## 創発余白と保護

国家ID、経路、係数は初期条件。future role、failure turn、recovery route、chosen route等はschemaで受理しない。係数が将来結果へ影響することは認め、その結果を先に物語へ固定しない。

未来にどの国家が協力するか、どの経路を使うか、どの資源が不足するかは保存していない。複数の候補経路、共有容量と在庫の別制約、input/outputの静的依存、国家別の非対称な国内状態が、後続の独立判断と相互作用の余地になる。

V1/V2、既存Simulation Engine、研究結果、旧JSON、第1・2段階の実装・baselineには変更を加えない。第4段階へ進まない。
