# 保存入力の読み取り診断：最初の1件で停止

2026-09-21 JST。初回Local pilotで見られた返答の反復を調べるため、保存入力から事実を抜き出す診断を行いました。
**予定4生成のうち1件を実行し、返答のJSONに重複キーがあったため停止。残り3件は未実行です。**
シミュレーションの実行回数・完了ターン・創発の観測数には含めません。

## 条件と、実際に起きたこと

入力は初回pilotのECON・第1ターンの送信本文を省略せず使用しました。元のAgent指示は、
actor・turn・自国の食料在庫・activity_resultsを抜き出す診断用の指示へ置き換えています。
seedは10073。予定していた入力2件×seed 10073／20073の答え合わせ用データは、生成前に固定しました。
診断用の返答はAgentや世界へ戻していません。

| 項目 | 入力に記録された値 | 実際の返答の原文で確認できること |
| --- | --- | --- |
| actor／turn | ECON／1 | ECON／1と記載 |
| 自国の食料在庫 | 数値75 | MILの在庫レコード（balance 68）を記載 |
| activity_results | 空の配列 | 別の活動・仕様に関する内容を記載 |
| 返答のJSON | 重複キーのないオブジェクトを要求 | `target`などのキーが重複し、厳密な読み取りで拒否された |

この表は不正な返答の原文を照合した説明であり、返答を修復して有効なAgent判断にしたものではありません。
HTTP 200、生成終了理由stop、所要時間75.03秒、入力10,156 tokens・出力640 tokens。
サーバーログの抜粋では入力切り捨て0、追加RAM prompt cache無効を確認しています。

モデルはOllama 0.34.2の `qwen3:1.7b`、digest
`8f68893c685c3ddff2aa3fffce2aa60a30bb2da65ca488b61fff134a4d1730e7`。
context 16,384、出力上限2,048、think=false、truncate=false、shift=false。
その他の取得済み設定と全送信内容はmanifest／RAWにあります。
課金API・自動再試行・回答修復・世界の更新はすべて0です。

## 証拠と照合

- [条件と診断の範囲](diagnostic-reading-3aaf1ecc-ed57-46b4-b21c-1f3dacf315fe/manifest.json)
- [RAW：事前に固定した4件の条件・正答、実際の1件の入力と返答、停止記録](diagnostic-reading-3aaf1ecc-ed57-46b4-b21c-1f3dacf315fe/RAW/)
- [failureの終了台帳](diagnostic-reading-3aaf1ecc-ed57-46b4-b21c-1f3dacf315fe/terminal.json)
- [DERIVED：生成済み1件・解析済み0件・未実行3件の区別](diagnostic-reading-3aaf1ecc-ed57-46b4-b21c-1f3dacf315fe/DERIVED/failure-analysis.json)

`DERIVED/assessment.json` の `completed_diagnostic_calls: 0` は解析と照合が終わった返答の数です。
実際には1件の生成応答を受信・保存しています。補足集計はこの違いを明示し、元の集計を上書きしていません。
診断コード・起動設定のhashは保存していますが、診断専用のローカル補助スクリプトはこの公開一式に含めません。
実際の送信JSON・受信本文・取得したモデル情報は保存しています。

リポジトリ直下で、モデルを呼ばずに内容を照合できます。

```bash
python -B tools/verify_evidence.py results/local-v4/diagnostic-reading-3aaf1ecc-ed57-46b4-b21c-1f3dacf315fe --expected-evidence-hash d6010e8e797faaec9a3a18fc114c42bf0ea04a15e0998505553849d96713f612
```

RAWの照合値は `d5b11bf52b613100ef0d9ea63e4a5b5ad564673b03581cdcda40b4b6a14cadea`。
取得元のコード版は `f163c343d4f89a5835278a0b145c837f20af6425`。
既存Evidence Formatに従う全11ファイルはローカル記録と全バイト一致する複製です。
ハッシュは記録の整合性を確認するもので、第三者による実行証明ではありません。

## 判断の限界と次工程

この1件は、現条件のまま大量観測へ進む根拠にはなりません。一方で、4件すべて失敗した、
モデルが常に誤読する、Agentの反復の原因が解明できた、という結論も出せません。
明示的な読み取り診断は、自由対話中の自発的な理解とは別の課題です。

当初の停止条件に従い、残りの診断・2ターン試走・大量実行への拡大を止めました。
今後の条件やモデルの変更は別の案として扱います。望ましい行動を教えて解決したことにはしません。
以前のpilotと、V1〜V4の指示・世界ルール・画面・保存結果は変更していません。
