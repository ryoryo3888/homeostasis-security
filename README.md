# HOMEOSTASIS SECURITY

## 世界の恒常性シミュレーション

HOMEOSTASIS SECURITYは、Geminiを用いたマルチエージェントシミュレーションです。
国家間の緊張、誤認、信頼、回復力などが、対話・情報共有・国際法という制度的制約によってどのように変化するかを8TURNで可視化します。

## 完成版の実験条件

- A国：慎重外交型
- B国：慎重外交型
- 国際法：あり
- Hotline：あり
- TURN数：8
- 実Geminiによる本番実験結果

## 提出対象の完成版

- Dashboard：`dashboard_v1.html`
- 本番結果JSON：`simulation_result_cautious_cautious_law_hotline_run1.json`
- 地球画像：`earth_japan_network_v2.png`

リポジトリには開発過程、比較実験、バックアップのファイルも含まれていますが、提出対象の完成版は上記Dashboardと本番結果JSONです。

## 完成版を見る

```bash
git clone https://github.com/ryoryo3888/homeostasis-security.git
cd homeostasis-security
python3 -m http.server 8000
```

サーバーを起動したら、ブラウザで次のURLを開いてください。

<http://localhost:8000/dashboard_v1.html?layout-final=1>

リポジトリのルート <http://localhost:8000/> を開いた場合も、完成版Dashboardへ自動的に移動します。

完成済みの本番結果を閲覧するだけであれば、Gemini APIキーや追加のPythonライブラリは不要です。必要なのはPythonの標準HTTPサーバーだけです。

サーバーを終了するには、起動したターミナルで `Ctrl+C` を押してください。

## シミュレーションを再実行する場合

新しいシミュレーションを実行する場合に限り、Gemini APIキーと`google-genai`が必要です。本番結果の閲覧には必要ありません。

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install google-genai
python3 simulation.py
```

APIキーはGitへ保存せず、実行時の入力だけに使用してください。
