# homeostasis-security

AI multi-agent simulation exploring why some worlds go to war while others do not.

## Pythonで実行する

### 初回セットアップ

リポジトリのルートで、uvを使って仮想環境を作成し、必要なライブラリをインストールします。

```bash
uv venv --python 3.13
source .venv/bin/activate
uv pip install google-genai
```

### シミュレーションを実行する

リポジトリを開くたびに、最初に仮想環境を有効化します。

```bash
source .venv/bin/activate
python simulation.py
```

実行時に `Gemini API Key:` と表示されたら、自分のGemini APIキーを入力してください。入力した文字は画面には表示されません。

### 結果をブラウザで見る

仮想環境を有効化した状態でHTTPサーバーを起動します。

```bash
python -m http.server 8000
```

ブラウザで <http://localhost:8000> を開いてください。サーバーを終了するにはターミナルで `Ctrl+C` を押します。

仮想環境を終了する場合は次を実行します。

```bash
deactivate
```


## Codexの使い方

ターミナル（黒い入力画面）で`codex`と入力する
もしくは、VSCode上でファイルを開き、右上のChatGPTのアイコン（うずまき）を押すと開ける

s