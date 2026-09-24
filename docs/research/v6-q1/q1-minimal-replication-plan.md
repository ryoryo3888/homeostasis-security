# Q1 Minimal Replication Plan

1. Q1と同一のWorld仕様・Leader設定・Observation・Action schema・promptを固定。
2. 新seedを複数用意し、同一初期条件のA/B paired runを作る。
3. A/B条件を反転したpaired runを含める。
4. 13TURNを超えて52TURNまで継続し、各TURNのcheckpointを保存。
5. 判断→外交→制度→契約→資源→物流→到着→利用→World Mutation→Metricを同一executionで記録。
6. 反証基準：差分がseed変更・A/B反転で再現しない、または長期化して回復差が成立しない場合は該当仮説を支持しない。

本計画は作成のみ。次実験・API呼出し・V6変更は未実施。
