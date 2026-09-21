# HOMEOSTASIS SECURITY — Research Finding #1

## Pre-registration: Candidate 3 / consent-chain boundary

**登録日:** 2026-09-21  
**状態:** 実験前に固定。未実行。  
**追加API実行:** 0回  
**対象:** 既存V3 paid-expanded Candidate 3の独立検証  
**RAW:** 変更しない。新しい集計はDERIVEDとして別保存する。

## 1. 選定したCandidate

**Candidate 3:** 有限資源の世界で、物理的な資源移転の成立は、資源の存在だけでなく、Agentの提案・同意・撤回の連鎖と結び付いて分岐するか。

このCandidateを選ぶ理由は、同じbaseline/networkに対して、既存RAWにGemini armとdeterministic controlの両方があり、full transaction、consent、withdrawal、arrival、shortageを同じEvidence系で追跡できるためである。V5では、同意・撤回・資源制約・タイミングのうち、どれを一つ外すと世界線が変わるかへ接続できる。

この登録は「同意が原因である」と確定するものではない。まず独立runで方向と反例を確認し、因果を主張できるかを判定する。

## 2. Research Question

同じ初期world・network・turn数・choice catalogueを保ったとき、Agentが作る同意・拒否・撤回の連鎖は、transaction settlement、到着量、累積shortageの結果と一貫して結び付くか。

## 3. 仮説

### H1: 事前仮説

Gemini Agent armでは、deterministic controlと比べて、同意拒否または撤回が多いrunほど、full transaction数と到着resource unitsが低く、累積shortageが高くなる方向が観測される。

### H0: 反証側

同意・拒否・撤回の違いがあっても、transaction、arrival、shortageの方向差が再現しない。または差の大部分がstock・route・reserveなどの物理制約だけで説明できる。

H1/H0は結果を見て変更しない。

## 4. 独立変数・従属変数

### 独立変数

- Agent arm: `gemini` または `deterministic_control`
- Gemini armの観測された consent chain: `explicit_yes_all_listed`、`explicit_no_all_listed`、`self_withdrawals`、`incoming_refusals`
- 事前登録seed（run間で固定値を変える）

consent chainは自然言語出力から観測された値であり、これだけで因果操作とは扱わない。

### 従属変数

- `transactions.full`
- `transactions.partial`
- `transactions.not_established`
- `arrived_resource_units`
- `cumulative_shortage.energy`
- `cumulative_shortage.food`
- `reason_codes`
- 完走、schema failure、timeout、parser failure、interrupted

## 5. 固定条件

既存V3 paid-expanded protocolの次の値を固定する。

- baseline digest: `1e59d0b69c643b39f30413e3ed5b9b3ba25f3124dca28518fad5e9b68ab45566`
- network digest: `8f341e91d2aa1653ac985040dacdb382eef8c768b4f863e2bbc25345b9599cec`
- provider: Gemini
- model: `gemini-3.5-flash-lite`
- states / Agents: `ECON`, `FOOD`, `FRAGILE`, `ISLAND`, `MIL`, `NEUTRAL`, `RES`, `SMALL` の8状態
- turns: 5
- temperature: 0.3
- thinking level: minimal
- max output tokens: 1536
- consent schema: 提示されたchoice IDごとにbooleanを返す。未提示のchoiceを追加しない
- world rules、resource units、reserve、route、choice catalogue、settlement、arrival、shortageの実装を変更しない
- 新しい制度、Coordinator、fallback、回復則、Agentへの結果命令を追加しない

deterministic controlは、同じbaseline/network/seedを用い、既存protocolの決定論的controlとして保存する。GeminiとLocal pilotは同じ母集団に混ぜない。

## 6. Seed・run数・実行単位

- independent attempts: **5回**
- 新規seed: **53、59、61、67、71**
- 既存seed 17、23、41は再利用しない
- 各seedについてGemini armを1回、対応するdeterministic controlを1回保存する
- 5回終了後に必ず停止する
- API失敗・timeout・schema failureも削除せず、attemptのEvidenceとして保存する

同じseedによる生成一致は保証しない。runの一致判定は保存されたworld/resultと事前登録した指標で行う。

## 7. 再現判定

### 方向一致（部分再現）

5つのseed-pairのうち**3組以上**で、次の両方を満たす場合を「H1方向の部分再現」とする。

1. Gemini armの`transactions.full`が同seedのdeterministic controlより少ない。
2. 同じpairで`incoming_refusals`または`self_withdrawals`が1件以上ある。

この判定は因果の証明ではなく、Candidateの方向が独立runでも現れたかの判定である。

### 強い方向一致

5組のうち**4組以上**で、上記1・2に加え、Gemini armの`arrived_resource_units`がcontrolより少ない、または累積shortageのenergy/foodのいずれかが高い場合。

### 非再現

有効なpairが3組以上あり、上記の方向一致が**0〜1組**の場合。2組の場合は「混合結果」とし、支持・反証のどちらにも分類しない。

### 技術的不成立

5 attemptsのうち2件以上がschema failure、timeout、parser failure、interruptedで完走しなかった場合、研究仮説の支持・反証を判定せず「技術的に判定不能」とする。失敗runは正式Evidenceとして残す。

## 8. 分析方法

1. seedごとにGemini/controlを対応付け、各RAW pathとhashを記録する。
2. run単位で上記の指標を表にする。成功runだけを選別しない。
3. H1の方向一致数、非再現数、混合数、技術失敗数を報告する。
4. `reason_codes`を拒否・reserve・stock・minimum amount等に分け、同意系と物理制約系を別列で示す。
5. 追加の合成指標、相関、統計的有意性は、事前登録していないものを確認的結論として使わない。
6. AgentをLeaderと呼ばず、どのAgent・発言・関係・タイミングが分岐に現れたかを記述的に保存する。

## 9. 停止条件と費用上限

- 5 attemptsの保存と集計が終わった時点で停止。
- +5 run、大量run、V5実装へ自動移行しない。
- 既存3 seedのuncached推定費用 `$2.5325984` を線形換算した5-run目安は約 `$4.22`。実行前に実際のinput/output tokenと料金表を再確認する。
- 事前の費用目安を超える見込み、model/provider変更、schema変更、未登録retryが発生した場合は停止して記録する。

## 10. 想定される反証結果

- Gemini armとcontrolのfull transaction・arrival・shortageが同方向に分かれない。
- 拒否・撤回が多くても物理結果が変わらない。
- 結果差が同意ではなく、stock・route・reserveの不足だけで説明できる。
- 5runの大半が技術失敗になり、Agent判断を評価できない。

いずれも失敗として削除せず、Research Finding #1の反証または未確定結果として保存する。

## 11. Evidence保存

追加runでは各attemptについて、run ID、seed、provider/model、取得可能なmodel version/digest、generation config、experiment/world config、timestamp、success/failure/interrupted、raw evidence hash、request/response path、world state/event pathを保存する。RAWはimmutable、集計・判定・図表はDERIVEDへ分離する。

**この登録の時点ではAPIを呼んでいない。** 次の実行は、登録内容を変更せずに5 independent runsを行う段階である。
