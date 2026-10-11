# タグ橋渡し（Tag Bridge）— 英語 tagger と日本語タグの検索・表示

- **日付**: 2026-10-12
- **状態**: proposed（仕様: [tag-bridge.md](../specs/tag-bridge.md)）
- **関連**: [tags.md](../specs/tags.md), [query-language.md](../specs/query-language.md), [model-stack-rollout.md](../plans/model-stack-rollout.md)（M4 `inferred_ja`）

## コンテキスト

- `auto_tagger` は booru 系 **英語**タグ（密度が高いが日本語話者には読みにくい）。
- `filename` / pixiv 由来は **日本語**で、意味が重なることがある（例: 制服 ↔ `serafuku`）。
- **一括で検索できれば便利**だが、DB 上で tagger タグを日本語に **書き換える**のは provenance や再バッチと相性が悪い。
- 全 tagger 語彙（数万）の辞書は **不要**。実用に効くエントリだけ **半自動候補 + 手動確定**で足していく。

## 決定

1. **保存データは英語のまま** — `image_tags.source='auto_tagger'` は変更しない。
2. **Tag Bridge** — 別ファイルの **エントリ一覧**で「代表ラベル（主に日本語）」↔「複数 source のタグ」を結ぶ。
3. **検索** — ユーザーが `tag:制服` や bridge ラベルを選ぶと、API がエントリを **OR 展開**して既存の tag 検索を実行する。
4. **表示** — 詳細の Tagger チップ等で、bridge にヒットすれば **括弧付き日本語ラベル**などを付ける（原文は残す）。
5. **辞書の規模** — 全 tagger 網羅ではなく、**数十〜数百エントリ**を目安に増やす。
6. **M4 `inferred_ja` とは別** — bridge は「既存タグの束ね方」、M4 は master + d1 で **新規日本語 flat を付与**。

## 保存場所と編集 UX（localStorage + サーバー push）

**正本（canonical）**: サーバー上の 1 ファイル（既定 `data/tag_bridge.json`）。git に含めるかは個人語彙のため **任意**（`.gitignore` 推奨可）。

**編集用ドラフト**: mockup（5199）設定 UI では **localStorage** にドラフトを持つ。

| 操作 | 動作 |
|---|---|
| API 接続・設定を開く | `GET /api/settings/tag-bridge` → サーバー内容をドラフトに読み込み（未保存変更がある場合は確認） |
| 一覧で追加・編集・削除 | **localStorage のみ**更新。画面上「未保存」表示 |
| **サーバーに保存**（push） | `PUT /api/settings/tag-bridge` — 検証後に JSON をファイルへ書き込み。成功したらドラフトを clean に |
| **破棄** | サーバーから再取得してドラフトを上書き |
| **エクスポート / インポート** | ファイル JSON（バックアップ・別 PC 用）。import はドラフトに載せ、push で正本へ |

**localStorage だけで編集 → push でサーバー** — この流れでよい。理由:

- 設定パネルでの連続編集が速い（毎キーストロークで API を叩かない）。
- 正本はサーバー 1 か所なので、**検索 API はファイルだけ見ればよい**（ブラウザごとに辞書がバラけない）。
- mockup 未接続 / API オフ時も、ドラフト編集 + export だけは可能。

**v1 の衝突**: 複数ブラウザ同時編集は **最後の push が勝つ**。必要になったら `updated_at` + 確認ダイアログ。

## 半自動候補（実装フェーズ）

| 段階 | 内容 |
|---|---|
| 手動 | 設定 UI で `label` + `auto_tagger:serafuku` 等を追加 |
| 詳細から | Tagger チップ →「橋渡しに追加…」で label を入力 |
| 共起（後） | 同一画像の filename タグ × tagger タグの共起 Top N を **候補**表示。採用でエントリにコピー（自動マージしない） |

## 理由

- [tags.md](../specs/tags.md) の方針「filename と tagger は統合しない」「エイリアス辞書は検索ブリッジ用」と一致。
- UI で試しながら辞書を育てる Phase 2 延長として mockup 設定に置くのが自然。
- 検索 OR は **API 側**必須（mockup だけだと curl・将来クライアントで再実装になる）。

## 代替案（不採用）

| 案 | 不採用理由 |
|---|---|
| tagger を DB 上で日本語化 | 再タグ・外部ツール・スコアと不一致 |
| 全 Danbooru EN→JA を取り込み | メンテ・ノイズ・個人コレクションと合わない |
| 辞書を localStorage のみ | 端末ごとに検索結果が変わる |
| 編集のたびに PUT | 遅い・途中失敗しやすい |

## 影響 / follow-up

- 仕様: [specs/tag-bridge.md](../specs/tag-bridge.md)
- クエリ: [query-language.md](../specs/query-language.md) §Tag Bridge
- **実装計画**: [tag-bridge-implementation.md](../plans/tag-bridge-implementation.md)
- roadmap: M4 より **先に bridge 単体**でも価値あり（既存 4 万枚を触らない）
