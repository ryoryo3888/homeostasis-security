# 過去資料の保管

修正前のソースの控えと、照合済みの重複結果・中間集計をまとめています。
新しい実験結果や現在の実行入口ではありません。

| 保管先 | 内容 |
| --- | --- |
| [legacy-pages](legacy-pages/) | 過去の画面ソース25件と空の`index.html.txt`。26件 |
| [legacy-python](legacy-python/) | 過去のPythonソース。9件 |
| [legacy-figures](legacy-figures/) | 過去の比較図4件。現行の図は元の場所に保持 |
| [legacy-bytecode](legacy-bytecode/) | 過去の実行キャッシュ1件。現行実行では使用しない |
| [duplicate-results](duplicate-results/) | 保持側とバイト一致した重複4件 |
| [legacy-derived](legacy-derived/) | 統合集計に同じ採点列がある中間物2件 |
| [unregistered-json-moves.json](unregistered-json-moves.json) | 追加6件の移動記録。[判断根拠](../docs/UNREGISTERED_JSON_AUDIT.md) |
| [manifest.json](manifest.json) | 移動元、移動先、内容のSHA-256、移動前commit |

初回40件と追加6件の計46件ともファイル内容は変更していません。原本を削除する整理ではなく、置き場所の整理です。
現在の入口は[README](../README.md)、版とファイルの対応は[リポジトリ案内](../docs/REPOSITORY_MAP.md)にあります。

過去のHTMLはソース資料として保管しています。相対パスを含むため、このフォルダでの画面動作は保証しません。
旧バックアップのroot URLも移動対象で、現行V1〜V4の公開URLとは区別します。
当時の配置が必要な場合は台帳の`source_commit`から別の作業場所へ復元できます。
移動台帳と既存の保護用ハッシュの両方をテストで照合しています。

初回の40件整理では実験結果や失敗記録を移していません。追加調査では重複4件と中間集計2件だけを移し、固有の結果・失敗関連記録は元の場所に保持しています。
名前に`previous`や`backup`があることだけを理由に、実験データを除外・削除しないでください。
