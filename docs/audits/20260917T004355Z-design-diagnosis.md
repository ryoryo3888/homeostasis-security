# 8TURN入口失敗の独立設計診断

対象: `20260917T004355Z-c09ce05c`。比較: 成功したfresh 1TURN `20260917T001606Z-c7bae18f`。
今回の外部Gemini/有料API呼び出しは0。原本と既存研究結果を変更しない。

## 変更前の事実と診断

1. **事実**: 失敗は最初の地球調整機関、完了0TURN、1 transport予約試行、retry 0。transportがUnicodeEncodeErrorを捕捉してfailedを永続化し、gatewayもFAIL・model_response=nullを記録。SDKから回答が返る前に停止した。providerへの到達・課金は記録から不明。
2. **原因仮説**: (A) credential等のHTTPヘッダー値が非ASCII、(B) 環境によるbackend/proxy/SDK差、(C) 日本語prompt/JSON/schema、(D) audit/checkpoint/file/consoleのencoding、(E) 8TURN固有の処理、(F) SDK内部・応答処理の別のencoding障害。
3. **証拠**: 成功/失敗の最初のpublic_observation_payloadは完全一致（UTF-8で1653 bytes）。modelは両方gemini-3.6-flash、schema_version=2。33da81eとfaf4646のMakefile、research_workflow、gemini_agents、api_budgetソースも同一。SDK内ではキーをx-goog-api-keyヘッダーへ置き、httpxは文字列ヘッダーをASCIIエンコードする。実SDK2.20.0＋httpx0.28.1＋HTTPモックで、ASCII合成キーと日本語payloadは成功、非ASCII合成キーはmock dispatch 0のUnicodeEncodeErrorを再現した。
4. **反証・限界**: この再現は当時のキーが不正だった証明ではない。当時の秘密値・環境・依存版・例外encoding・発生フレームが未記録なのでA/B/Fは確定不可。Cは同一payloadが成功しUTF-8エンコード可能であることと整合しない。Dのcheckpointは明示UTF-8で、保存失敗ならAuditPersistenceErrorへラップされる。今回のtransport内でのUnicodeEncodeErrorとは一致しない。通常のCLI表示はSDK呼び出し前後であり、主因の可能性は低いがSDK内部loggingまでは否定できない。Eは最初の共通呼び出しより後のループ長しか変えない。モデルquota/validationなら通常は異なる例外だが、二次的なSDK encoding障害までは排除できない。
5. **最有力原因**: SDK/HTTP境界の設定値エンコード不適合（非ASCIIヘッダー値が最も具体的に再現可能）。UnicodeEncodeErrorは症状であり、「8TURNだから日本語に非対応」ではない。元runの入力値まで遡る根本原因は未確定。確定した装置側欠陥は事前検査欠落・失敗証拠不足・null回答exporterの二次障害。
6. **255テストが見逃した理由**: tools/check.pyはSDKをfakeモジュールへ置換し、モデルもfake。実SDK→HTTPヘッダー変換を通らない。失敗publicationの既存テストは不正な構造化回答中心で、回答未取得nullとclient初期化0試行が漏れていた。CIにもSDK導入・実SDK境界テストがなかった。PASSはシミュレーター契約の確認であり実ユーザーの認証・環境の保証ではなかった。
7. **追加の弱点**: source/SDK/locale/backend方針のrun記録なし、SDK暗黙環境依存、予約attemptとprovider受理・課金の混同、client生成がfailure捕捉の外、development入力の更新で旧snapshot検証が失敗、CLIの例外チェーンに秘密を含む可能性。残るリスクはSDK既定の待ち時間に依存すること（call数上限は時間上限ではない）、依存全体の完全lockなし、実provider認証/利用可能性は無料モックで証明不能、部分TURN resumeの再送/研究バイアス。CLIはresumeを公開しておらず、失敗runの再開は推奨しない。
8. **最小案**: credentialのASCII/制御文字検証、null回答の型安全な診断、秘密を含まない段階証拠、実SDK HTTPモック回帰。
9. **根本案**: すべてのrunに明示transport方針とruntime manifest・request hashを保存し、HTTP境界までを無料CIへ組み込む。providerの受理/課金は予約attemptから推定しない。失敗は正式研究外のまま自動観測する。
10. **次回の最小コスト案**: SDK依存を更新して無料make check PASS後、別途許可した既存probeを最大1 call、retry 0で実施して停止。同じclient/endpoint/model/transport方針で実認証・接続を確認する。probeの国Agent payloadと最初の調整機関payloadは異なるが、後者は保存fixtureでSDKモック往復を検証済み。probe成功だけで8TURN自動進行せず、結果に応じてfresh 1TURNを判断する。

## 1TURNと8TURNの実行経路比較

| 項目 | 実コード・保存証拠の比較 |
|---|---|
| CLI / Make | 同じmakeレシピ→research_workflow.main。modeのみturn/experiment。旧final_experiment_runner CLIも同じworkflowへ委譲 |
| environment | 同じ環境継承機構。実行当時の値・locale・依存版は両run未保存なので同一とは断定しない |
| client / model | 同じcreate_gemini_client→genai.Client、SDK attempts=1。保存model同一 |
| prompt | 最初のcoordinator payloadは保存JSONで完全一致 |
| response schema | 共通coordinator_response_schema。SDKへ渡した完全wire schemaは過去run未保存で、共通ソースから確認 |
| serialization | 共通json.dumps(...ensure_ascii=False)。SDKはHTTP JSONを生成しUTF-8で転送。日本語のASCII化・削除は不要 |
| HTTP | 共通BoundedClient→SDK。修正前のbackend/proxy等はSDK環境依存。生HTTP記録なし |
| logging / stdout | 共通CLI予定表示。保存失敗はtransport内なので通常の表示処理よりSDK境界が有力。SDK内loggingは証拠不足 |
| audit writer / checkpoint | 共通UTF-8 atomic checkpoint。失敗runには送信前と失敗後の監査が残る |
| results directory | 両方rejected/run_idで開始。成功1TURNはprobeへ移動、失敗experimentはrejectedに残る。入口時のカテゴリ差なし |
| locale / encoding | 当時未記録。今回のローカルはPython3.13.15、UTF-8。過去runの証拠へ代用しない |
| metadata / TURN数 | turn=1/上限10とturns=8/上限80。最初のSDK payloadには総TURN数もexperiment固有metadataも入らない。研究metadataは完走後生成 |
| 研究昇格 | 1TURNは常に対象外。experimentのみ8TURN完走後の厳格validate_research。今回失敗runは対象外のまま |

## 実装した修正

- credentialをclient生成前に検証。非ASCII・空白・制御文字を定数メッセージで拒否し、値・長さ・hashを保存しない。有効な認証かどうかは無料検証では判定しない。
- SDKはtrust_env=FalseでもSSL_CERT_FILE/DIRを読むため、同期・非同期・内部WebSocket初期化のTLS contextにcertifiを明示。合成の不正CA環境パスでもmock往復が成功することを確認。
- backend=Gemini Developer API、公式endpoint/v1beta、retry=0、trust_env=Falseを明示。環境proxy/CA/別backendへの暗黙切替は使用しない。意図的なproxy運用が必要なら将来明示設定として検証する。
- SDK自動function callingを明示的に無効化。choice-ID/strict validation/atomic settlementは変更なし。
- exact requestの有限JSON/UTF-8検査とhash、local_request_validation / sdk_entered / sdk_returnedを監査。失敗証拠は型・encoding許可値・ライブラリ群のみ。例外本文、UnicodeError.object、ヘッダー、SDKオブジェクト、locals、内部推論は保存しない。
- runtime.jsonにsource commit/digest、Python/SDK/HTTP版、encoding分類、明示方針、環境設定の存在booleanだけを保存。旧runには後付けしない。
- client初期化も失敗捕捉対象とし、0試行とnull回答失敗をresearch対象外のままpublication可能にした。CLIには秘密を含み得る元例外チェーンを表示しない。
- exporterのnull回答処理とdevelopment state再生成を修正。既存runは通常のmake publish-statusで再読込可能。
- make checkに実SDK＋HTTPモック4件を追加。CIは固定SDK/HTTP依存を導入後、ネットワーク遮断で実行する。依存未導入ならチェックは失敗し、SDK境界を未検証のままPASSにしない。

## Codexの改善提案

優先順: (1) 今回の境界テストと失敗段階記録を維持、(2) 次の実認証確認は1-call gate、(3) 明示的なrequest timeoutを運用要件に合わせて設計し、Python/全依存lock・実行manifest照合を強化、(4) provider request IDを将来安全に取得できる場合だけ受理証拠として追加、(5) TURN境界の明示pause/resumeは予算の永続継承と重複防止・選択バイアス方針を設計してから導入。単純な自動retryや途中TURNの再送は追加しない。Agentの回答・理由を条件達成のために変更しない。

正確なチェック結果・追加テスト・次段階は [development state](../../results/status/development.json) を参照。今回の根本原因の確度と過去runの失敗判定は、無料テストPASSによって書き換えない。

最終無料検証: make check PASS（265件＋実SDK HTTPモック4件）、無料preflight PASS、API calls 0。過去run 22ファイルのハッシュ不変を確認。
