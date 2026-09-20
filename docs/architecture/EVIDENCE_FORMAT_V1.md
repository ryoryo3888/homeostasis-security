# Evidence Format 1

大量観測前に固定する最小の保存形式。最終的な研究設計・評価指標を決める文書ではない。
順序は、この形式の検証 → ローカルLLMの少数試行 → 実験記録のGitHub保存。
Agentの自由、世界の条件、指標の意味と限界は[観測前の説明](OBSERVATION_TRANSPARENCY.md)を参照。

- `manifest.json`：run ID、開始時刻、seedと適用範囲、provider/model、取得できるモデル版・digest、実際のgeneration config、実験・世界設定、ソースハッシュ・commit・runtime・継続元・試行目的。
- `RAW/`：実際の入力・応答、世界の初期状態と推移、event・transfer・shock、実行時の計測、失敗。モデルの発言と世界で実行された結果は区別する。
- `terminal.json`：success / failure / interrupted、終了時刻、完了ターン数、エラー種別、manifestとRAW全ファイルのハッシュ。
- `DERIVED/`：RAWから計算した集計。参照元のRAW全体ハッシュを必ず記録する。

各JSONは`{"sha256": <canonical payload hash>, "payload": <record>}`で保存する。
RAW全体ハッシュは、相対ファイル名からファイル全バイトのSHA-256への対応表を、
既存`homeostasis_v3.contracts.canonical`で直列化したSHA-256。
独立したevidence hashはmanifest・RAW・terminalを結び付ける。外部に保存したこの値を
指定すれば、全ファイルを書き換えてハッシュを付け直した場合も検出できる。
ハッシュ一致だけでモデル提供元の真正性を証明したとは言わない。

保存は上書き禁止。停止・timeout・parser failureも残す。強制終了でterminalが
ない場合は`unfinalized`であり、成功に数えない。終了時刻は推測しない。
取得できなかった版・指定しなかったseed等はnullとし、理由を設定・来歴に記録する。
同じseedによるLLMの出力一致は保証しない。保存応答からの世界再生と、再生成実験は別。

検証入口：`python -B tools/verify_evidence.py <run-directory> --expected-evidence-hash <pin>`。
これはファイルの整合性検査。世界の再生・モデル応答の妥当性は実行側でも検証する。

公開対象は実験プログラムが生成した記録だけ。利用者と制作AIの相談ログ、認証情報、
個人のファイルパスを収集しない。公開前に対象と秘密情報を確認する。
既存の過去記録は移動・上書きせず、不明な条件を後付けで作らない。
