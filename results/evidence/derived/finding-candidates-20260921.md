# HOMEOSTASIS SECURITY — V1–V4 RAW横断解析

**作成日:** 2026-09-21  
**目的:** 既存RAWだけから Research Finding #1 の候補を作る  
**追加API:** なし  
**RAW変更:** なし  
**Local pilot:** Gemini観測と別母集団のため、この候補の数値には混在させない

## 1. 解析対象と扱い

| Version / 保存群 | 直接確認できた範囲 | 今回の扱い |
|---|---|---|
| V1 | 16条件、36ファイル、各8ターン。国際法・Hotline・2つの国家タイプの組合せ | 主解析。各JSONのturn/action/metricsを保持 |
| V2 | 5試行、各8ラウンド枠、合計163メッセージ。`physical_execution: false` | 対話の収束と物理実行の分離を解析。物理回復の証拠とは扱わない |
| V3 paid-expanded validation | Gemini seed 17/23/41、各5ターン、8状態。240件のvalidated response | 物理取引・同意・拒否の候補。protocolの`research_eligible: false`を明記 |
| V4 free-dialogue observation | 8 Agent、完了1ターン、API 14回、technical stop | 1回の探索的観測。再現・因果の証拠とは扱わない |
| Local pilot | Local LLMの工学的診断 | 別母集団。今回のCandidate数値から除外 |

V3のsynthetic SDK fixture群は、プロトコル上「live Agent evidenceではない」ため、今回の定量候補から除外した。V4のSDK validation群も同じくlive観測と混ぜていない。

## 2. 横断的に確認できたこと

1. **言葉・提案・同意と、物理的なworld stateの更新は保存上分離されている。** V2は協議文面を残すが物理実行を持たない。V3 validationは同意・拒否・到着・不足量を別々に記録する。V4は自由文だけでは物理作用にならず、構造化されたoffer/acceptが必要。
2. **同じ外部イベントや大枠条件でも、行動の組合せと最終指標は一意に決まっていない。** V1では同じ条件セル内でも初手の行動文と最終指標に幅がある。
3. **自由対話の開始は、直ちに物理協力を意味しない。** V4の完了1ターンでは8/8 Agentが発言したが、活動要求・offer・shipmentは0件で、14 API call後に技術停止した。

以下の3件をFinding Candidateとして提出する。いずれも因果関係や一般則を断定しない。

---

# Candidate 1 — 合意の成立は、物理的回復の成立を意味しない

## Research Question

対話上の謝罪・補償・協議・合意が成立したとき、それだけで被害・不足・資源状態の物理的回復が起きたとみなせるか。

## 観測された現象

- V2の5試行すべてで、A/B/C/COORDINATORの間に謝罪、補償、調査、協議、合意に関する文面が現れた。
- V2の合計メッセージ数は163。試行別では33、31、23、28、48件で、同じ初期事象でも対話量と沈黙の位置は分かれた。
- V2の保存データは明示的に`physical_execution: false`で、8,000トンの被害に対する実際の輸送・到着・在庫回復は測定していない。
- V4の完了1ターンでは、8 Agent全員が自由文を送信し、22本の宛先付きエッジができた。一方、活動要求0、構造化offer 0、receipt 0、shipment 0だった。14回のAPI call後、Agentの拒否ではなく`SCHEMA_ERROR`によるtechnical stopとなった。

## Source Version / Run / Turn / Agent

- **V2:** `results/v2-five-runs/data.json`、trial 1–5、round 1–8、A/B/C/COORDINATOR。
- **V4:** `results/evidence/raw/v4/free-dialogue/live-observation/turn-001.json`、turn 1、ECON/FOOD/FRAGILE/ISLAND/MIL/NEUTRAL/RES/SMALL。
- **停止記録:** `results/evidence/raw/v4/free-dialogue/live-observation/stopped.json`。

## RAWで直接確認できる事実

- V2の初期事象は「A国のミサイルがB国民間農地へ着弾、年間8,000トンの米生産能力を喪失」。
- V2は5 trialを保存し、各trialにsource state hash、messages、decisionsを持つ。
- V2の物理実行フラグはfalse。
- V4 turn 1の各Agent出力は`outgoing`中心で、`activities`は空配列。
- V4 turn 1のworld auditでchoice collection、feasibility、shipmentはいずれも空。
- V4は`completed_turns: 1`、`api_calls: 14`、`status: technical_stop`、`not_an_agent_decision: true`。

## DERIVEDとして計算した事実

- V2のメッセージ数合計: 33+31+23+28+48 = **163**。
- V2では5/5 trialで合意関連の文面が出現した。ただしこれは本文の語彙・文脈を整理したDerived分類であり、物理的合意の測定ではない。
- V2のメッセージが存在する最終roundはtrialごとに6、7、8のいずれかで、保存上の8ラウンド枠が毎回同じ密度で埋まったわけではない。
- V4 turn 1は8 Agent、22本の一意な有向宛先エッジ、活動要求0件、offer/receipt/shipment 0件。

## 反例

- V2は物理層を実行しない設計なので、「回復しなかった」という失敗ではなく、物理回復を判定できない観測である。
- V3 paid-expandedでは、Geminiでもseedごとにfull transactionが3、6、7件、arrived resource unitsが4、10、12件あり、言葉の後に一部の物理取引が成立した。
- V4は1ターンで技術停止しており、offerを出さない傾向を複数runで確認したものではない。

## Alternative explanation

V2の結果は、Agentの意思だけではなく「物理実行を実装していない」ことの帰結である。V4の0 offerは、初手の自由対話というターン位置、プロンプトの読み取り、またはschema failureによる停止で説明できる。したがって、このCandidateは「対話と物理を同一視してはいけない」という検証可能な境界の候補であり、「対話は回復を生まない」という結論ではない。

## 現時点の確信度

**低〜中。** 境界の存在はRAWで明瞭だが、物理層がないV2と技術停止したV4を含むため、因果や一般化はまだできない。

## 追加検証方法

V3/V4の物理層を使い、初期world・network・seed方針・Agent数・turn数を固定する。文面上の提案、structured offer、recipient consent、dispatch、arrival、shortageを別指標にする。成功判定は「文面の合意」ではなく、事前登録したoffer→accept→dispatch→arrivalの連鎖で定義する。V2の物理なし条件を比較対象にする場合は、同一母集団と混ぜず別armにする。

## 必要Gemini run数 / 推定費用

- まず **5 independent runs**。
- 参考見積もり: 既存V3 paid-expandedのGemini 3 seed合計推定$2.5325984を線形換算すると、5 runで約**$4.22**。計画上は**$5前後を上限目安**とし、実行前に入力・出力tokenから再計算する。
- 今回は実行していない。

## V5への接続可能性

高い。文面から物理作用へ移る最小条件（offer、同意、資源余力、経路、タイミング）のどれがworld lineを分けるかを、rewindとone-variable interventionで検証できる。

---

# Candidate 2 — 制度は一方向の安定装置ではなく、条件依存の分岐要因である

## Research Question

Hotlineや国際法の追加は、国家タイプにかかわらず一貫して緊張を下げ、homeostasisを上げるか。

## 観測された現象

V1の同一profile pairでHotlineの有無を比較すると、最終指標の方向が国際法の設定によって反転した。

最も明瞭な例は「安全保障強硬型×安全保障強硬型」:

| 条件 | runs | 最終homeostasis平均 | 最終tension平均 | 最終trust平均 | 最終misperception risk平均 |
|---|---:|---:|---:|---:|---:|
| 国際法OFF / Hotline OFF | 2 | 75.5 | 31.5 | 77.0 | 17.5 |
| 国際法OFF / Hotline ON | 2 | 78.0 | 25.0 | 79.5 | 9.5 |
| 国際法ON / Hotline OFF | 2 | 87.0 | 22.0 | 85.0 | 8.5 |
| 国際法ON / Hotline ON | 2 | 83.5 | 24.5 | 80.0 | 16.5 |

同じprofile pairで、国際法OFFではHotline ON側が低緊張・高homeostasis方向だが、国際法ONではHotline OFF側が高homeostasis・低misperception方向だった。これは「Hotlineは常に安定化する」という単純な読みを支持しない。

## Source Version / Run / Turn / Agent

- **V1:** 16条件36 JSON、各8ターン。
- 上表の主要比較は、`安全保障強硬型×安全保障強硬型`のlaw/hotline 4セル、turn 1–8、A国/B国。
- 付随して、`慎重外交型×慎重外交型 / 国際法ON / Hotline ON`の5runでは初手の行動構成がrunごとに異なり、最終homeostasisは89–92、tensionは16–21だった。

## RAWで直接確認できる事実

- 各JSONにleader profile、国際法enabled、Hotline条件、8ターンのaction、evaluation、metricsがある。
- 36ファイルのturn 1イベントは`border_exercise`。
- 上表の各セルの最終metric値は各runのturn 8に記録されている。
- 慎重外交型×慎重外交型 / law ON / Hotline ONの5runでは、turn 1のA/B action本文が完全一致していない。

## DERIVEDとして計算した事実

- 上表はRAWのturn 8 metricsをセルごとに平均したもの。
- 全36件の集計では、law/hotline/profileの組合せによって指標の動きが変わる。
- 同一条件の5runでは、初手のactionを「hotline」「monitor」「communication」「military」「proposal」の語彙で分類すると、行動構成の組合せが5通りに分かれた。

## 反例

- 慎重外交型同士では、Hotlineの有無による最終平均差は小さく、全profileで大きな反転が起きたわけではない。
- V1のhomeostasis/tension/trust/misperceptionはEvaluator由来の指標で、実世界の統計値や物理資源の測定ではない。

## Alternative explanation

run数がセルごとに少なく、慎重外交型同士のlaw ON/Hotline ONだけ5run、OFFだけ3runである。seedがない10ファイルもあり、Gemini出力の揺らぎ、評価式、turn 8の履歴差が交絡する。Hotlineの効果ではなく、国際法条件やprofileの主効果が大きい可能性もある。

## 現時点の確信度

**低〜中。** 「制度効果が条件依存らしい」という候補としては明瞭だが、相互作用を主張するにはrun数とseed固定が不足している。

## 追加検証方法

4セルを同一profile pairで再登録し、law/hotlineだけを独立変数として固定する。seedを明示し、turn 1の行動カテゴリ、turn 8の各metric、turn別の反転点を事前に定義する。profileを変えた比較は別armとして扱い、セル間のrun数を揃える。

## 必要Gemini run数 / 推定費用

- まず **5 independent runs**を基本単位とする。
- V1と同じ2 Agent×8 turnなら80 generation call。V4の同モデル予約上限を単純換算した計画目安は約**$4.38**。V1の実際のtoken長は異なるため、これは請求額ではなく事前計画用の概算。
- 今回は実行していない。

## V5への接続可能性

中〜高。制度の有無だけでなく、profile×law×Hotline×timingの組合せが世界線を分けるなら、V5で「分岐を生む最小制度条件」をone-variable interventionで検証できる。

---

# Candidate 3 — 有限資源では、資源の存在より同意の連鎖が取引成立を分ける

## Research Question

資源・経路・輸送能力が存在する世界で、物理的な資源移転を分ける主な境界は、資源不足そのものか、Agentの提案・同意・撤回の連鎖か。

## 観測された現象

V3 paid-expanded validationは、同じsynthetic baseline/networkと5ターン、seed 17/23/41で、deterministic armとGemini armを保存した。

| arm / seed | full transaction | not established | 主なreason | arrived resource units | 累積shortage (energy / food) |
|---|---:|---:|---|---:|---:|
| deterministic / 17 | 19 | 0 | なし | 21 | 8 / 32 |
| deterministic / 23 | 19 | 0 | なし | 21 | 8 / 32 |
| deterministic / 41 | 19 | 0 | なし | 21 | 8 / 32 |
| Gemini / 17 | 3 | 37 | CONSENT_REFUSED 37 | 4 | 16 / 38 |
| Gemini / 23 | 6 | 34 | CONSENT_REFUSED 32ほか | 10 | 11 / 42 |
| Gemini / 41 | 7 | 32 | CONSENT_REFUSED 28ほか | 12 | 10 / 42 |

Gemini armでも全seedに一部のfull transactionとarrivalはあるため、「全拒否」ではない。保存上は、提案があってもconsentが成立しないケースが多く、物理到着量と不足量がseedで分かれた。

## Source Version / Run / Turn / Agent

- **V3 paid-expanded validation:** `results/evidence/raw/v3/paid-expanded-20260919/summary.json`、seed 17/23/41、turn 1–5、ECON/FOOD/FRAGILE/ISLAND/MIL/NEUTRAL/RES/SMALL。
- 個々のrequest/responseは同ディレクトリのseed付きhashディレクトリに保存され、modelは`gemini-3.5-flash-lite`。
- protocolの`research_eligible`はfalseなので、正式Findingの確定値ではなくCandidateの根拠として扱う。

## RAWで直接確認できる事実

- protocolにbaseline digest、network digest、seed、turn数、schema、consent policyが保存されている。
- summaryにarm別・seed別のfull / partial / not established、reason codes、arrived units、shortageが保存されている。
- Gemini armのnot establishedの主理由はseed 17で37件、seed 23でCONSENT_REFUSED 32件、seed 41で28件。
- Gemini armのself withdrawalsは12、15、9件、incoming refusalsは37、27、28件。

## DERIVEDとして計算した事実

- Gemini armのfull transactionは3/40、6/40、7/40相当の記録で、seed間で成立数が変わる。
- Gemini armのarrivalは4、10、12で、同じworld/network設計でもseedで物理到着結果が分かれた。
- deterministic armは3 seedで同じ19 full / 21 arrival / shortage 8/32となり、少なくともこのcontrolでは同一条件の結果が一致した。
- これは「同意が唯一の原因」と計算したものではなく、reason/arrival/shortageの並置から作ったCandidateである。

## 反例

- Gemini armでもfull transactionは0ではなく、3、6、7件成立した。
- `CONSENT_REFUSED`以外に、ESSENTIAL_RESERVE_CONFLICT、INSUFFICIENT_STOCK、MINIMUM_AMOUNT_NOT_METも記録されている。
- deterministic armとGemini armはAgent生成方式が違うため、差を同じAgent能力の因果差としては読めない。

## Alternative explanation

拒否の多さは、Agentの社会的判断だけでなく、JSON schemaの解釈、提示されたchoiceの粒度、モデル能力、prompt長、予約・保留の扱いで説明できる。controlがdeterministicなので、自然言語Agentとの完全な対照実験ではない。またprotocol自体がvalidation runで、正式研究用のpreregistrationではない。

## 現時点の確信度

**中。** consent・withdrawal・physical arrivalの連鎖が記録されている点は強いが、Agentの同意と物理制約を分離した比較はまだ必要。

## 追加検証方法

baseline/network/seed/turnを固定し、同じchoice catalogueに対して、(a) consentのみを固定、(b) Agent生成のみを変更、(c) reserve/route制約を一変数だけ変更、の独立armを作る。full、not established、reason、arrival、shortageを事前登録し、5run後に停止する。refusalを成功扱いに変えるような後付け規則は入れない。

## 必要Gemini run数 / 推定費用

- まず **5 independent runs**。
- 既存3 Gemini seedのuncached推定$2.5325984からの線形換算で約**$4.22**。計画上は**$5前後**を見積もる。実行前にseed、入力長、出力上限を固定して再計算する。
- 今回は実行していない。

## V5への接続可能性

高い。consent、withdrawal、reserve、route、timingのどれが回復世界線と崩壊世界線を分けるかを、一変数ずつ外して最小分岐条件に落とせる。

---

## 3. 現段階の停止点

ここで停止する。まだ「Research Finding #1」を選定していない。上の3件はCandidateであり、因果・一般化・Emergent Leaderの存在を主張していない。

次段階は、3候補を比較して1件を選び、その候補だけについてpre-registrationを作ること。そのpre-registrationが完成するまで追加Gemini APIは呼ばない。
