# V4ローカルLLM pilot

[透明化の説明](OBSERVATION_TRANSPARENCY.md)と[証拠形式](EVIDENCE_FORMAT_V1.md)を先に固定し、
M1・8GBで小型モデルを実際に動かすための接続。Agentへの共通指示、初期状態、
同時入力、私的情報の境界、有限資源・輸送・同意の法則を変更しない。

初期候補はOllamaの`qwen3:1.7b`。無料のローカル実行のみ。
クラウド無効、127.0.0.1への接続限定、モデル名・digest・版を実行前後と各呼出前に確認する。
モデルの用意は実行器とは別に行い、実行器は自動ダウンロードや有料APIへの切替を行わない。
Ollama 0.34.2のAPIを確認対象とする。別の版は再確認まで拒否する。

試行の既定値は2ターン・8国家・最大16生成、context 16,384、出力上限2,048、think=false。
生成seedはrun seedに呼出番号を足した値。温度等の未指定値は、保存したモデルパラメータと
固定版サーバーの既定値を使う。Geminiと同じサンプリング条件だとはみなさない。
これらは実行を検査するpilotの条件であり、研究の最終条件ではない。

入力省略とcontextの切り捨てを禁止するため、`truncate=false`と`shift=false`を送る。
上限で途切れた返答は完了とせず、原文を残して技術的失敗とする。
自動再試行、回答の修正、望ましい回答の選び直しは行わない。
接続・読取等のHTTP timeoutは180秒、次の呼出を開始できるrunの時間枠は1,200秒。
HTTP timeoutは通信操作ごとの制限で、run全体の厳密な強制終了時刻ではない。

## 入口

1. `python -B tools/run_v4_local.py --prepare --model qwen3:1.7b --seed 73 --turns 2`。
   モデルへ生成要求を送らず、ローカル環境・条件とそのdigestを取得する。出力を準備ファイルとして保存する。
2. `python -B tools/run_v4_local.py --execute --prepared <prepared.json> --output <new-directory>`。
   その条件で一度だけ実行し、Evidence Format 1へ保存する。既存出力へ上書き・再開しない。
3. `python -B tools/run_v4_local.py --replay <run-directory>`。
   モデルを呼ばず、RAWの送信内容と実応答を各checkpointに照合し、初期状態から順に世界を再生する。

RAWには実際に送ったsystem/prompt/options、HTTP応答本文、途中受信分、時刻と所要時間、
メモリの観測、世界checkpoint、失敗を残す。モデル情報は公開に必要な項目の取得記録で、
個人の絶対パスを含む生成Modelfileは保存対象から除外する。
失敗もterminalとRAWを保存し、CLIは非0終了する。強制終了でterminalが残らない場合はunfinalized。

DERIVEDの実行集計はRAWのハッシュを参照する。メモリは時点サンプルであり、
連続計測した厳密なピークではない。RSSとGPU割当を別に記録し、単純な和を実消費とみなさない。
保存応答で世界が再生できることと、同じseedでモデルが同じ返答を再生成することは別に確認する。

数を増やすのは、応答の書式・入力理解・時間・メモリ・ログ量を実測で確認してから。
pilotの失敗や未対応要求も捨てず、生ログ公開は取得・検証の後に行う。
合成HTTP応答によるテストは`synthetic-transport`と明示し、実Agentの観測数へ含めない。

API確認根拠：[公式API型](https://github.com/ollama/ollama/blob/v0.34.2/api/types.go)、
[公式サーバー処理](https://github.com/ollama/ollama/blob/v0.34.2/server/routes.go)、
[ローカル実行・クラウド無効](https://docs.ollama.com/faq)、
[モデル](https://ollama.com/library/qwen3:1.7b)。
