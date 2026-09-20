# HOMEOSTASIS SECURITY — 保存済み実験RAW

このディレクトリは、保存済みの実験記録を世代別に公開するための証拠置き場です。今回の公開作業では新しいAPI実行やシミュレーションを行っていません。

## 構成

- `raw/` — 保存済みの入力、Agent応答、wire/sdk記録、world state、turn、checkpoint、journal。V1・V2・V3・V4・Local pilotを世代・実行群ごとに分離しています。
- `derived/` — RAWから作った棚卸し、SHA-256対応表、公開前のsecret/privacy scan、完全性記録。RAWの代わりに使うデータではありません。
- `provenance/` — 追加の出典説明を置くための領域です。世代や実行群の意味は各RAWの保存構造と、リポジトリの研究文書を照合して確認してください。

## 保持方針

元のローカルRAWは変更していません。`derived/raw-inventory.json`に、元ファイルのパス、元SHA-256、公開コピーのSHA-256、バイト完全一致かどうかを記録しています。Local pilotの8ファイルに含まれていたホスト上のモデル親パスだけは公開コピーで伏せています。観測内容、要求、応答、world stateの値は変更していません。

公開前スキャンは `derived/secret-privacy-scan.json` に保存しています。APIキー、Bearer token、GitHub token、秘密鍵などの秘密情報パターンは検出されず、公開コピーに残ったprivacy findingもゼロでした。

V3の`preflight`やV4の`sdk-validation`は、実験観測と技術検証を区別できるように別の実行群として残しています。これらを正式な研究結論やモデル間の優劣へ自動的に集計してはいません。
