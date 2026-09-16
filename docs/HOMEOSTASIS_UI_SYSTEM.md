# HOMEOSTASIS SECURITY UI SYSTEM

Status: visual design contract for v1, v2 and future extensions.

## 1. 最重要原則

HOMEOSTASIS SECURITY は一つの研究シリーズとして、各Dashboardの**見た目のフレームだけを統一**する。

**Fixed visual shell + version-specific content.**

ここでいう「統一」は、既存Dashboardの情報量・文章量・グラフ・研究内容・データ・機能を削ったり再構成したりすることではない。

### 絶対に変えないもの
- v1の既存文章量・情報量
- v1の既存グラフ、表、研究詳細、16条件、TURN表示、データ
- v2の既存文章量・情報量
- v2の既存グラフ、タイムライン、イベントログ、Agent情報、データ
- 各バージョン固有の研究構造と機能
- 既に成立している表示内容と操作

**文字が多いことは問題ではない。文字量を減らすことを目的にしない。**

統一対象は、背景、外枠、パネルの形、ヘッダー、余白、色、フォント階層、ボタン形状、TURN操作の視覚言語、カードの表面処理などの「見た目」。

## 2. 共通フレーム

v1 / v2 / 今後の拡張で、可能な範囲で次を同じ視覚言語にする。

1. HOMEOSTASIS SECURITY ブランド／ヘッダーの外観
2. バージョンナビゲーションの位置・形
3. dark navy 系背景
4. cyan primary / magenta secondary の基本アクセント
5. パネルのborder / radius / translucent fill / glow
6. typography hierarchy（内容そのものは変更しない）
7. spacing / gap / dashboard outer width の基本ルール
8. TURNボタンの形・active表現
9. KPIカードの表面デザイン
10. Agentカードの表面デザイン
11. Event Logの表面デザイン
12. chart / timelineを囲うフレーム・凡例の視覚言語
13. responsive時の基本的な視覚ルール

既存のコンテンツ構造を無理に同じ列数・同じカード数へ変更しない。

## 3. 中央Earthは各バージョン固有

フレームは統一するが、中央の地球は研究の進化を示す場所なので統一しない。

### v1
- A国 ↔ B国の通信・相互作用
- 現在の二国間Earth表現を保持

### v2
- 衛星3機が異なる軌道を周回
- 現在の地球規模観測Earth表現を保持

### v2追加／8国家版
- 8国家・資源・地球調整機関など、その研究に必要なEarth表現を追加可能
- ただし外側のDashboardフレームはv1/v2と同じ視覚言語を使う

将来の拡張でも同じ考え方を使う。

## 4. 共通デザイントークン（基準）

以下は見た目の基準。既存画面をこれへ合わせる際も、コンテンツや研究データを変更しない。

```css
:root {
  color-scheme: dark;
  --hs-bg: #030b14;
  --hs-bg-deep: #07111d;
  --hs-panel: #071827;
  --hs-panel-2: #0b2132;
  --hs-line: rgba(91,220,247,.20);
  --hs-cyan: #67e8f9;
  --hs-cyan-2: #22d3ee;
  --hs-magenta: #d88cff;
  --hs-amber: #fbbf24;
  --hs-green: #34d399;
  --hs-red: #fb7185;
  --hs-text: #edf7fb;
  --hs-muted: #96afbb;
  --hs-radius: 14px;
  --hs-gap: 10px;
  --hs-panel-bg: linear-gradient(180deg,rgba(8,27,42,.94),rgba(3,15,25,.95));
  --hs-panel-shadow: inset 0 0 30px rgba(34,211,238,.025), 0 16px 45px rgba(0,0,0,.22);
}
```

## 5. 既存コンテンツ保全ルール

UI統一作業では、見た目を揃えるために既存内容を編集してはいけない。

### v1
- グラフを削除・簡略化・別形式化しない
- 表を削除・簡略化しない
- 文章量を減らさない
- 研究詳細を下へ移動する等の再配置を勝手に行わない
- 16条件やTURN操作を変更しない
- EarthのA/B通信表現を変更しない

### v2
- 文章量を減らさない
- Agent情報を削らない
- KPIを削らない
- タイムライン／グラフ／Event Logを削除・簡略化しない
- 5TURN等、現在の研究内容をUI統一目的で変更しない
- 衛星3機を含むEarth表現を変更しない

### 将来の追加版
- その研究に必要な文章・表・グラフ・Agent情報はそのまま保持してよい
- 「文字が多い」という理由だけで削除・図式化しない
- 統一するのはあくまで外観とコンポーネント表現

## 6. 共通コンポーネントの外観

### Panel
radius / border / background / glow / padding family を共通化する。
中に入っている内容はバージョンごとに異なってよい。

### KPI
label / value / optional mini bar の見た目を揃える。
KPIの種類や個数は研究内容に従う。

### Agent card
枠、見出し、ラベル、本文の文字階層を揃える。
表示項目・文章量は削らない。

### Event Log
枠、TURNラベル、accent、行間等を揃える。
ログ内容・件数は変更しない。

### TURN control
button geometry / active state / arrow style / current-turn emphasis を揃える。
TURN数や操作機能は各研究のまま。

### Graph / table
データ、系列、軸、値、表構造は変更しない。
外枠、タイトル、legend、background等の外観のみシリーズとして近づける。

## 7. 言語ルール

- 日本語中心という既存方針を維持する。
- 既存文章を短文化しない。
- 英語system labelは既存デザイン上必要な範囲で使用可能。
- UI統一を理由に文章をグラフへ変換したり、グラフを文章へ変換したりしない。

## 8. 変更してよいもの／いけないもの

### 変更してよい（視覚）
- background
- panel border / radius / fill / shadow
- header visual treatment
- version switch visual treatment
- font size / weight / color hierarchy（意味や本文を変えない範囲）
- spacing / padding / gap（内容を欠落させない範囲）
- button visual treatment
- card visual treatment
- graph container / legend visual treatment

### 原則変更しない（内容・構造）
- 文章内容・文章量
- グラフの種類・データ・系列
- 表の内容
- KPIの意味・値
- Agent情報
- Event Log内容
- TURN数
- 実験条件
- 研究結果
- 各バージョン固有のEarth演出
- 機能

## 9. Visual-only regression gate

統一作業後、次を確認する。

- v1の情報が一つも失われていない
- v1のグラフ・表・文章が維持されている
- v2の情報が一つも失われていない
- v2のグラフ・タイムライン・文章・ログが維持されている
- v1 EarthはA/B通信のまま
- v2 Earthは衛星3機のまま
- TURN等の既存操作が維持されている
- そのうえで、スクリーンショットを並べた時に同じHOMEOSTASIS SECURITYシリーズだと分かる

## 10. 実装順序

1. 公開mainは触らない。
2. `homeostasis-ui-system-20260916` で作業する。
3. v1/v2の既存内容・機能を固定したまま、視覚差分だけを比較する。
4. 共通化するCSS／フレーム要素だけを決める。
5. v1/v2へvisual-only変更を適用する。
6. 内容・グラフ・データ・操作が変わっていないことを確認する。
7. その共通フレームを将来の8国家版へ使用する。
8. main統合・公開はRioの明示許可後のみ。

## 11. Source-of-truth rule

今後AIがHOMEOSTASIS SECURITYを拡張するときは、**「既存コンテンツを共通テンプレートへ作り直す」のではなく、「既存コンテンツを保持したまま共通の外観を着せる」**。

研究内容が増えれば文字・表・グラフが増えてよい。シリーズ統一の対象は情報量ではなく、視覚フレームである。
