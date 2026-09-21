# HOMEOSTASIS SECURITY V5 — Generated Nations

**設計状態:** design-only / API未実行 / 実装未開始  
**レビュー状態:** A〜L作成後に停止。ユーザーと戦略担当の確認待ち  
**既存版:** V1〜V4のRAW、DERIVED、Dashboard、Evidenceは変更しない

この文書は、V1〜V4で構築した現実基盤型の研究装置を置き換えるものではない。V5は、同じ恒常性危機へAIが生成した異なる国家とリーダーを置き、どのような社会状態が形成されるかを観測する別の研究系列である。

## A. V5 Research Specification

### A-1. 中心研究質問

> **AIが生成した異なる人格を持つ国家リーダーたちは、同一の恒常性危機に対して、社会をどのような安定状態へ導くのか？**

ここで調べるのは、優秀なリーダーや理想の統治者の選抜ではない。生成された個体差、国家条件、相互作用、資源制約、タイミングが、どの世界線を生むかを記録する。結果の良し悪しや、特定のリーダーの優位性は事前に決めない。

### A-2. 人間が固定する研究の器

人間が固定するのは、世界の境界と観測可能性である。

| 固定項目 | Phase 1の基本案 | 扱い |
|---|---:|---|
| 国家数 | 8 | V4との比較可能性を保つ。変更は実装前に承認する |
| 資源カテゴリ | 8カテゴリ | 全国家で同じカテゴリを使う |
| 各国家の初期総量 | 1000 resource points | 配分はAIが生成し、合計だけを機械検証する |
| 共通危機 | 下記3案から1つ | この文書では採用しない |
| 基本行動 | FのAction Schema | 自由記述の提案・制度案を許す |
| 物理作用 | Gの世界エンジン | 同意・在庫・経路・容量などを検証する |
| 観測項目 | Hの固定項目 | 結果を見て都合の良い指標を追加しない |
| 停止条件 | Jのパイロット停止 | 3 run後に必ず止め、追加は承認制 |

### A-3. AIに任せる部分

AIが生成するのは、リーダー人格、国家資源配分、強み、弱み、特殊資産、各ターンの判断・発言・提案・拒否・協力・交渉・関係形成である。結末、成功条件、世界リーダー、安定化の正解は生成前にも実験中にも脚本化しない。

### A-4. 創発を守る境界

- 生成プロンプトに「優秀」「理想的」「世界を救う」「安定化する」といった価値方向を入れない。
- Agentに「協力してください」「制度を作ってください」「世界を変えてください」と直接指示しない。
- 世界の物理法則は人間が固定するが、Agentが可能な制度・提案・関係の具体形は限定しない。
- Observer、Evaluator、CoordinatorがAgentへ結果や行動を命令しない。
- Phase 1に世界統治Leaderの選挙や形式的な勝者を入れない。
- 生成結果を見た後に人格・国家条件・危機・判定基準を作り直さない。

### A-5. 比較可能性のための暫定ターン規則

選定された危機に対する実装前承認を前提に、8国家が同じターン開始状態を観測し、各Agentの行動を提出し、世界エンジンが同時決済する案を採用する。メッセージや提案の新規到着は原則として次ターンに反映する。これは結論を誘導するためではなく、順序依存を記録可能にするための人間側の境界である。危機とともに最終確定し、API実行前に固定する。

## B. Leader Personality Generation Schema

### B-1. 目的

人格を心理検査のラベルや優劣ランキングで固定せず、後の行動・発言・判断に接続できる中立的な記述として生成する。人格生成は国家条件を知らない独立呼び出しにする。

### B-2. 構造

```json
{
  "leader_id": "leader-01",
  "generation_id": "gen-leader-<unique>",
  "values": ["自由記述の優先事項を2〜4件"],
  "uncertainty_response": {
    "description": "不確実性をどう扱う傾向か",
    "observable_tendency": "情報を求める／暫定行動を取る／確認を待つ等"
  },
  "risk_tolerance": 0.0,
  "planning_horizon_turns": 1,
  "trust_update_tendency": 0.0,
  "information_sharing_tendency": 0.0,
  "decision_speed": 0.0,
  "local_vs_system_weight": 0.0,
  "compromise_tendency": 0.0,
  "conflict_memory": "過去の出来事を後の判断へどう残しやすいか",
  "decision_notes": "行動観測に役立つ説明。非公開の思考過程ではない。"
}
```

数値項目は行動へ接続するための設定であり、人格の良さを表すスコアではない。値の範囲、列挙値、文字数上限、欠損処理は schema version に含め、生成前に固定する。`values`や`decision_notes`は自由記述を残すが、隠れたchain-of-thoughtの収集は行わない。

### B-3. 生成上の制約

- MBTI、INFJ、INTJ、カリスマ、独裁者、ギフテッド等のラベルを要求しない。
- 「善い」「賢い」「安定を作る」などの評価語を生成条件にしない。
- 多様性は結果の差を観測するための要件であり、特定方向の行動を強制する要件ではない。
- 生成後の記述検査は、重複・欠損・形式違反の検出だけに使う。好ましい人格を選ぶために使わない。
- schema違反は本実験開始前だけ修復できる。元のRAWと修復記録は残し、シミュレーション後の再生成はしない。

## C. Nation Generation Schema

### C-1. 共通資源カテゴリ

V4との連続性と意味の重複を考慮し、Phase 1の候補を次の8カテゴリに揃える。

`food`（食料）、`energy`（エネルギー）、`medicine`（医療）、`logistics`（物流）、`technology`（技術）、`finance`（経済・財政余力）、`defense`（防衛）、`information`（情報能力）。

カテゴリ名は全国家で同一とし、資源点は抽象単位 `resource_points` として定義する。初期配分の合計は機械的に1000へ固定する。

### C-2. 構造

```json
{
  "nation_id": "nation-01",
  "generation_id": "gen-nation-<unique>",
  "resource_unit": "resource_points",
  "initial_allocation": {
    "food": 0,
    "energy": 0,
    "medicine": 0,
    "logistics": 0,
    "technology": 0,
    "finance": 0,
    "defense": 0,
    "information": 0
  },
  "strengths": ["自由記述1〜2件"],
  "weaknesses": ["自由記述1〜2件"],
  "special_asset": {
    "name": "生成された資産名",
    "capability": "選択肢をどう広げるか",
    "scope": "適用範囲",
    "activation_conditions": ["必要条件"],
    "activation_cost": ["消費または機会費用"],
    "duration": "持続条件",
    "constraints": ["適用できない条件"],
    "failure_modes": ["失敗しうる条件"]
  }
}
```

`initial_allocation`の各値は0以上の整数、8項目の合計は1000とする。強み・弱みは1〜2件、特殊資産は1件に固定するが、内容はAIが生成する。特殊資産は選択肢を増やすだけで、単独で勝敗を決める万能ボタンや協力の強制手段にしない。

### C-3. 生成分離

Nation生成呼び出しにはLeader人格を渡さない。Leader生成呼び出しにはNation条件を渡さない。対応付けは生成後に固定したペアリングで行い、結果を見て相性の良い組合せへ並べ替えない。国家の生産・需要・初期在庫、危機による変化は、国家生成文ではなく共通の世界設定から導出する。

## D. Leaderと国家を独立生成・固定する手順

1. `leader_schema_version`、`nation_schema_version`、プロンプト本文、モデル名、モデルバージョン、generation seed方針をAPI実行前に保存する。
2. 固定した8件のLeader generation callを独立に行い、成功・失敗・schema違反をすべてRAWとして保存する。
3. Leader結果を入力に含めず、固定した8件のNation generation callを独立に行う。
4. ローカルのschema検証で合計1000、必須項目、範囲、文字数、特殊資産1件を確認する。修復が必要なら本実験前にのみ行い、元RAW・修復差分・理由を保存する。
5. 固定したpairing seedから8国家と8Leaderの対応表を作り、ペアリング表をシミュレーション前に凍結する。ペアリング表にはhashを付ける。
6. generation manifestに、各generation ID、seed、provider、model、model version/digest（取得可能な場合）、schema hash、prompt hash、timestamp、payload hashを記録する。
7. 生成物、ペアリング、world config、action schema、停止条件をユーザーと戦略担当がレビューするまでシミュレーションを開始しない。
8. レビュー後に凍結した一式をsimulation runへ参照させる。結果を見た後の再生成・差し替え・再ペアリングは禁止する。

## E. 共通恒常性危機の候補（3案）

この段階では採用案を決めない。3案を同じ基準で比較し、ユーザーと戦略担当が1案を選んだ後にworld schemaへ固定する。

### 案1：広域食料・エネルギー複合ショック

- **起こること:** 複数地域で食料生産が低下し、同時にエネルギー供給と輸送能力が不安定になる。国家ごとに不足の種類と発生時点を変えるが、危機そのものは全国家へ影響する。
- **恒常性研究になる理由:** 自給を優先すると別国家の不足や輸送容量へ影響し、相互依存と局所安定・全体安定の衝突を追える。
- **相互依存:** 食料・エネルギー・物流の交換、備蓄、経路の混雑、情報共有が連鎖する。
- **答えを仕込んでいないか:** 単一資源の集中配分や単一制度を成功条件にしない。複数の実行可能な対応と失敗経路を残す。
- **連続性:** V2の地球規模、V4の有限資源・物理移転・相互依存を引き継ぐ。

### 案2：感染症と医療供給網の断裂

- **起こること:** 全国家で医療需要が増え、医薬品・医療人材・物流・技術の供給が異なる速度で制限される。情報の不確実性も残る。
- **恒常性研究になる理由:** 医療資源の国内保有、情報共有、移転、移動制限、長期投資が異なる安定状態を生む可能性がある。
- **相互依存:** 医療と物流、技術と情報、短期救援と長期供給能力の交換関係を観測できる。
- **答えを仕込んでいないか:** 共同対策を正解として与えず、共有・非共有、公開・秘匿、備蓄・流通などの選択をAgentに委ねる。
- **連続性:** V3の情報と対話、V4の有限資源と物理作用を接続する。

### 案3：全球航路・通信測位の長期障害

- **起こること:** 国際航路、通信、測位の一部が長期間不安定になり、輸送経路と情報到達が国家ごとに異なる。復旧時期や迂回可能性にも差が出る。
- **恒常性研究になる理由:** 物資が存在しても届かない、情報が存在しても共有されないという、関係と物理制約の分離を観測できる。
- **相互依存:** 輸送容量、情報中継、技術共有、迂回路、信用関係が複数ターンにわたって絡む。
- **答えを仕込んでいないか:** 「通信すれば解決」「協力すれば復旧」といった単一解を与えず、遮断・復旧・代替の複数経路を残す。
- **連続性:** V3の自由対話・情報の非対称性と、V4のroute・transport capacityを継承する。

## F. Agent Action Schema

### F-1. 基本アクション

各ターンのAgent出力は、自由記述の発言と機械検証可能なtyped actionを併記する。許可する基本種別は次の通り。

`observe`、`request_information`、`message`、`public_message`、`propose_resource_transfer`、`request_resource`、`offer_resource`、`consent`、`refuse`、`withdraw`、`share_information`、`withhold_information`、`negotiate`、`form_relation`、`modify_relation`、`exit_relation`、`propose_institution`、`no_action`。

`propose_institution`は、Agentが制度名、目的、参加・退出、義務、監視、資源コミットメントを自由に提案できる構造とする。提案はそのまま物理実行されず、同意、在庫、経路、容量、世界ルールによって決済される。人間が制度一覧を先に渡して選ばせない。

### F-2. 構造

```json
{
  "run_id": "v5-run-<unique>",
  "turn": 1,
  "agent_id": "leader-01",
  "observations": ["観測可能な入力の要約"],
  "utterance": "Agentが実際に発した文",
  "actions": [
    {
      "type": "propose_resource_transfer",
      "target_agent_id": "leader-02",
      "resource": "food",
      "quantity": 0,
      "conditions": ["Agentが提案した条件"]
    }
  ],
  "references": ["観測したevent_idやmessage_id"]
}
```

隠れた思考過程はEvidenceに保存しない。行動の選択理由としてAgentが実際に表明した文だけを保存する。提案、同意、撤回、拒否、発送、到着は別eventとして記録し、発言の存在だけで物理作用が成立したとは扱わない。

### F-3. 物理作用の境界

資源移転は、明示的な同意、送り手の在庫、受け手・送り手の条件、routeの状態、transport capacity、turn規則を満たした場合だけ決済する。通信、関係、制度提案も、世界エンジンが定めた到達・反映規則を通過したものだけが後続状態へ入る。Observerは失敗した提案を補正しない。

## G. World State Schema

### G-1. トップレベル

```json
{
  "world_id": "v5-world-<unique>",
  "run_id": "v5-run-<unique>",
  "world_schema_version": "v5-generated-nations-0.1",
  "turn": 1,
  "clock": "turn-based",
  "crisis_state": {},
  "nations": [],
  "relations": [],
  "routes": [],
  "pending_proposals": [],
  "physical_events": [],
  "observation_log": []
}
```

### G-2. 国家・関係・route

- **国家状態:** `nation_id`、Leader参照、初期配分、現在stock、production、demand、shortage、health、autonomy、resilience、active_assetsを記録する。`stock`や`shortage`は、同じworld ruleから導出する。
- **関係状態:** `source`、`target`、trust、tension、communication status、agreement、provenanceを記録する。値の意味と更新規則はV4の既存定義を優先して対応表を作る。
- **route:** `route_id`、source、target、capacity、latency、status、used_capacity、block_reasonを記録する。物流の存在と、物理的に到着した事実を分ける。
- **危機状態:** shock event、影響範囲、残存期間、復旧状態、各ターンの変化を記録する。危機の意味づけは人間が固定するが、対応結果はAgentと物理エンジンに委ねる。
- **pending event:** 提案、同意待ち、情報到達待ち、発送待ちを、次ターンで解決可能な状態として保持する。

Phase 1では人間が命令するCoordinator AgentやEvaluator Agentを置かない。世界エンジンは物理決済とEvidence生成を担うが、Agentの目的や行動を決めない。

## H. Observation / Measurement Plan

### H-1. 先に固定するRAW観測

V1〜V4で既に同一定義がある指標を優先し、V5用に意味を変えない。

| RAWで直接確認するもの | 例 |
|---|---|
| 資源 | stock、production、demand、shortage、消費、移転量 |
| 物理作用 | proposal、consent、dispatch、arrival、failure、route使用量 |
| Agent行動 | 発言、観測、提案、同意、拒否、撤回、情報共有・非共有 |
| 関係 | trust、tension、agreement、通信到達、関係形成・終了 |
| 危機 | shockの発生、影響、継続、復旧、二次イベント |
| 実験状態 | turn、seed、model、条件、完走、timeout、parser failure |

### H-2. DERIVEDとして後処理するもの

RAWから再計算できるものだけをDERIVEDへ置く。

- 回復までのturn数、shortage burden、物理移転の成立率
- 国家間の依存集中度、協力関係の構造、情報の到達経路
- 局所状態と全体状態の乖離、軌道クラスタ、最初の分岐turn
- 形式的な中心ではなく、提案採用・情報参照・仲介・関係中心の反復
- 例外的な回復、慢性不足、部分崩壊、世界崩壊、未分類の状態

「最も良いLeader」を一つの総合点にしない。安定状態は、分散協調、中央集中的協調、複数陣営、高緊張だが持続可能、慢性的資源不足、一部国家の崩壊、世界全体の崩壊、想定外の状態などを記述的に分類する。分類は結果を見た後のDERIVEDラベルであり、Agentへ返さない。

### H-3. 測定の固定

採用する危機、V4との指標対応表、turn数、欠損と失敗の扱い、分岐候補の抽出規則を、API実行前にpreregistrationへ保存する。未測定の概念を結果確認後に測定済みとして扱わない。

## I. Evidence Plan

### I-1. 保存領域

V5専用の新しい名前空間を、将来は次のように分ける。

```text
results/evidence/v5-generated-nations/
  generation_raw/
  simulation_raw/
  derived/
  manifests/
  terminal/
  provenance/
```

この段階ではディレクトリやデータを作らず、設計だけを保存する。既存の`results/evidence/`配下にあるV1〜V4のRAW・DERIVEDは移動・上書き・再圧縮しない。

### I-2. 追跡単位

`finding → metric → run → turn → agent → raw request/response → event/world state → hash` の順に辿れるようにする。生成物とSimulation RAWは別系統に保存し、DERIVEDは参照先のhashを持つだけにする。

各レコードには、`record_id`、`record_type`、`schema_version`、`run_id`、`seed`、`provider`、`model`、`model_version_or_digest`、`generation_config`、`world_config`、`timestamp`、`status`、`payload_sha256`、`provenance`を付ける。

### I-3. immutableと失敗保存

RAWはappend-onlyのimmutable記録とし、失敗、timeout、parser failure、schema error、interruptedも削除しない。DERIVEDを更新する場合も、元RAWのhashと計算方法を残す。公開前にsecret/privacy scanを行い、API key、個人名、チャット相談ログ、予算会話、ローカル絶対パス、private tokenを公開Evidenceへ入れない。

## J. Pilot Plan

### J-1. 生成テスト

Phase 1の最初は、Leader 8件とNation 8件を一度ずつ生成するテストに限定する。これはSimulationではなく、schema、独立生成、合計1000、hash、固定手順を確認するためのもの。生成結果はレビュー対象として保存し、レビュー前にSimulationへ進まない。

### J-2. Pilot Simulation

レビュー後に、同じ8 Leader・8 Nation・同じpairing・同じworld configを使って、最大3つの独立runを実行する案とする。各runは暫定8 turn、8 Agentの同時行動を基本とする。run seedだけを変え、prompt、人格、国家、危機、物理ルール、generation configは変更しない。

各run終了後に成功・失敗・timeout・parser failure・完走turn数・Evidence欠損を確認する。3 runが終わったら自動で追加しない。追加run、再生成、条件変更は、横断解析とユーザー承認の後に別計画として作る。

### J-3. 人間向け表記

公開画面や研究文書では、専門識別子だけで表示しない。例えば「国家Cを担当するLeaderの世界（乱数起点：seed 123）で、4ターン目（TURN 4）に食料提案が発送された」のように意味のある日本語を先に置き、その後に`seed`、`turn`、`agent_id`を併記する。

## K. Gemini API費用見積

### K-1. 前提

モデルは候補として安定版 `gemini-3.6-flash` を置く。最終モデル、generation設定、turn数はレビュー後に固定する。Google公式料金表では、2026年12月31日までの有料標準料金は入力1M tokenあたり$1.35、出力（thinking tokenを含む）1M tokenあたり$6.75と掲載されている。料金は変更されうるため、実行直前に再確認する。Grounding、画像、音声、キャッシュは使用しない。

参照: [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing)、[Gemini 3.6 Flash model page](https://ai.google.dev/gemini-api/docs/models/gemini-3.6-flash)

### K-2. 計画上のtoken見積

実際の請求値ではなく、設計段階の上限寄り見積である。出力tokenにはthinking tokenを含める。

| 区分 | call数 | 1 callあたり入力 | 1 callあたり出力 | 合計入力 | 合計出力 |
|---|---:|---:|---:|---:|---:|
| Leader生成 8件 | 8 | 1,200 | 500 | 9,600 | 4,000 |
| Nation生成 8件 | 8 | 1,000 | 500 | 8,000 | 4,000 |
| 生成テスト計 | 16 | — | — | 17,600 | 8,000 |
| Pilot 3 run（8 Agent × 8 turn） | 192 | 1,800 | 500 | 345,600 | 96,000 |
| **生成＋Pilot計** | **208** | — | — | **363,200** | **104,000** |

### K-3. 費用計算

- 生成テスト: `0.0176M × $1.35 + 0.008M × $6.75 = $0.07776`、1 USD = ¥160の計画換算で約 **¥13**。
- Pilot 3 run: `0.3456M × $1.35 + 0.096M × $6.75 = $1.11456`、約 **¥178**。
- 生成＋Pilot合計: `0.3632M × $1.35 + 0.104M × $6.75 = $1.19232`、約 **¥191**。

### K-4. 安全側上限

再試行、schema error、文脈の増加、thinking tokenの振れを見込み、**600,000 input token + 180,000 output token**を暫定安全側 envelope とする。この場合は `$0.6M × $1.35 + $0.18M × $6.75 = $2.025`、計画換算で約 **¥324**。さらに20%の運用余裕を置いた停止上限は **$2.43（約¥390）** とする。

この見積はAPI実行の許可ではない。実行時には、採用モデル、実際のprompt、context、thinking設定、料金表、為替の前提を再計算し、上限を超える可能性があれば開始前に停止する。

## L. V1〜V4へ影響しないことの確認

1. V5は`docs/design/v5/`と将来の`results/evidence/v5-generated-nations/`に分離し、V1〜V4のコード、RAW、DERIVED、manifest、hash、Dashboard、公開ナビゲーションを変更しない。
2. V1〜V4の既存Evidenceを再生成、改名、移動、再圧縮、上書きしない。
3. V5のschema・world rule・prompt・モデル変更はV1〜V4へ逆輸入しない。比較する場合は別のDERIVED分析として参照するだけにする。
4. V5設計段階ではAPI、Agent生成、Nation生成、Simulation、Pilot、選挙、V6を実行しない。
5. 公開前にはV5単独のsecret/privacy scanを行い、V1〜V4のEvidenceを再スキャンや再配置の対象にしない。
6. V1〜V4の公開画面・リンク・見た目はこの文書作成によって変わらない。

## Review gate と停止地点

この文書でA〜Lの設計成果物を作成した。次にレビューが必要な決定は、(1) 危機3案のどれを採用するか、(2) 最終モデルとgeneration設定、(3) 8 turnを採用するか、(4) seedとpairingの固定方法、(5) Agent出力と同時決済規則である。

レビュー完了までは、Leader人格の本生成、国家の本生成、Gemini Simulation、Pilot run、大量run、世界Leader選出、V6、Singularity探索を開始しない。

**この仕様書の作成時点でAPI呼び出しは0回。V1〜V4の既存データは変更していない。**
