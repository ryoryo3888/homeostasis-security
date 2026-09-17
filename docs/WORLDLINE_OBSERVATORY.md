# WORLDLINE OBSERVATORY — Phase 1

保存済み世界線を、作品から研究証拠まで連続した深さで読む。新しい実験を起動する機能は持たない。既存Dashboardを変更せず `worldline_observatory.html` を独立した入口とした。

正式基準: [Design / Research Principles](../DESIGN_RESEARCH_PRINCIPLES.md)、[Creative Research Roadmap](CREATIVE_RESEARCH_ROADMAP.md)。対象は `20260917T075421Z-11147417`。n=1の観測であり、実行成功と世界の改善を同一視しない。

## 体験と表示契約

最初の層は静かなタイポグラフィと8つの観測点。第二層は同じ選択TURNに対する条件・資源・復興のレンズ。第三層で国家を選び、choice → conditions → Python復元action → 決済 → source evidenceへ降りる。JSONはこの深さにだけ置く。

| 視覚 | データと意味 | 意味を持たないもの |
|---|---|---|
| 軌跡の高さ | `executed_state.true_world`、共通0〜100軸 | 線分は連続測定・時間補間ではない |
| Homeostasis円 | 面積が値/100に比例 | 心拍や追加の時間データではない |
| 国家間矢印 | `derived.condition_edges`、要求者→要求される国家 | 地理、同盟、二国間trust、線幅の強弱ではない |
| 破線の国家と× | 正式participantsに含まれない | 応答契約の不正を意味しない |
| 資源の輪郭/塗り/斜線 | atomic requested / realized / unmet、同資源内共通尺度 | 要求者を物理的なsourceと混同しない |
| pool線と面 | TURN開始値と決済後値、容量100 | 同TURNの新規拠出を同TURNの引出し源とみなさない |
| 復興の残存面積 | 初期損失を分母にしたafter | 農地回復から食料生産への未実装因果を描かない |
| 復興の内訳棒 | domestic_recovery / external_support、全TURN共通尺度 | モデル計上を現実の因果推定とみなさない |

T4の集中要求350→50、T6のSMALL条件不成立、T8の供与経験国の自己引出しは、TURN番号による分岐でなく、保存済みデータ上の述語から発見する。条件不成立でatomic記録がない場合は「移転記録なし」と表示し、ゼロ量の架空移転を作らない。公開理由はモデルの最終回答のみ。

数値は画面上小数3桁まで。証拠JSONの精度は維持する。モデル指標とシナリオtonsを混ぜない。eventの生成根拠、Coordinator提案、Evaluatorの公開評価は折りたたみから読む。

## 実装境界

- `observatory/view-model.js`: 原本を変更しない純粋投影。run / turn / field pointer / call_idを保持。契約PASS、カタログtuple、量、world指標、pool、flow収支を確認。
- `observatory/app.js`: DOM・SVGと操作のみ。simulation coreをimportしない。
- `observatory/config.json`: 公開timelineのパスとSHA-256。読み込み時にhash不一致ならfail-closed。同一originの公開ファイルだけをfetch。
- `tools/build_observatory.py`: secret scan後に静的allowlistをコピーしhash manifest生成。原本・checkpoint・SDK・キー・実行機能を収録しない。
- ブラウザには認証設定、キー入力、API実行ボタン、音、自動進行はない。CSPで外部接続と外部scriptを禁止。
- 依存パッケージ・外部フォント・CDNなし。将来のworldlineは同じtimeline schemaとconfigを使用する。現在は研究採用済み成功runのみを観測対象とし、失敗runは既存observabilityへ分離する。

## アクセシビリティ

HTML button・details・dialogを使用。Tab/Enter、レンズの左右矢印/Home/End、Escによるdialog終了、可視フォーカス、TURN切替後のフォーカス維持、aria-liveを提供する。色に加えて数値・矢印・斜線・破線・×を使う。動作補間や自動再生なし。reduced-motionでは開閉のfadeも無効にする。

## 品質評価と残る限界

| 領域 | Phase 1評価 | 次の改善 |
|---|---|---|
| Data Fidelity | 同一timeline、SHA-256、元カタログ照合、atomic実量。表示と証拠が対応 | 新schema導入時はアダプタと単位契約を追加 |
| Research Integrity | 原本不変、公開理由のみ、n=1・指標・未実装因果を明記 | モデル指標の較正は別の研究課題 |
| Interaction Clarity | 世界線→レンズ→判断→証拠の順、3つの実データ入口 | 初見ユーザーによる観察テストは未実施 |
| Visual Coherence | 共通尺度・暖色の恒常性・静かな余白、装飾フローなし | 高密度条件集合のラベル衝突対策 |
| Artistic Distinctiveness | 脈動や架空地理を足さず、配分不足と条件の構造を見せる | 独自性は自己評価。展示環境での体験評価が必要 |
| Engineering Quality | 純粋投影/DOM/静的buildを分離、hash pin、実ブラウザ検証 | app描画は規模拡大時にレンズ単位で分割 |
| Accessibility | 320/390/1440幅、数値併記、キーボード、reduced-motion | VoiceOver/NVDAによる実読上げと利用者検証は未実施 |
| Future Extensibility | run番号に依存しない観測primitiveと発見述語 | 複数worldline比較と不確実性表示は未実装 |

Phase 1はread-only研究作品としての入口。社会の予測製品としての完成宣言ではない。次は小規模な初見・キーボード・読上げレビューから、データと視覚の理解差を確認する。追加のGemini実験はこのUIのためには不要。

## 検証と配布

`make check` は既存のAPI遮断テストに静的buildのallowlist・hash改変拒否・frontend指紋を加える。`make observatory-check` は実Chromiumで純粋性・全decision/flow pointer・不正入力拒否・3現象・DOM操作・フォーカス・画面幅・reduced-motionを確認する。`make observatory-build` はsecret scanを含む。GitHub Actionsは3つとpublication validationを実行する。

ローカルはrepositoryルートをHTTP配信する。build成果物の新入口は `dist/observatory/worldline_observatory.html`。静的HTTPS配信は可能だが、この作業はホスティング設定変更・mainへの公開を行わない。
