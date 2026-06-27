# A2A 被管理サブエージェント規約（Mnemo 管理の子プロセス）

| 項目 | 内容 |
|---|---|
| 作成日 | 2026-06-16 |
| ステータス | 規約 v0.2（2 層分割。アーキテクチャ確定分。細部は §5 で順次確定） |
| 対象読者 | Mnemo が spawn・管理する A2A サブエージェントを実装する人 |
| 位置づけ | normative。Part B = 被管理サブエージェント層（**Part A を前提に追加義務を定める**） |
| 前提 | **Part A = [A2A_INTERFACE_CONTRACT.md](A2A_INTERFACE_CONTRACT.md) を必ず満たすこと**／根拠 = [ASYNC_JOB_RESEARCH.md](ASYNC_JOB_RESEARCH.md) §7 |

> このドキュメントは「Mnemo が spawn・管理する子サブエージェント」だけの**追加義務**を定義する。
> A2A プロトコル表面（タスク・SSE・push・Agent Card・MCP）の共通規約は Part A にある。
> **Part A を満たした上で、本書の S1〜S4 を満たすこと。**
>
> Mnemo 本体側の実装仕様（`jobs` テーブル・spawn 管理・通知連携の内部設計）は別途「実装仕様」で詰める。

---

## 0. 大原則

Mnemo に接続する被管理サブエージェントは、**独立したプロセスで動く独立したエージェントランタイム**である。
Mnemo 本体のコード（`ConversationManager` / tools / LLM 抽象）を import・共有してはならない。
サブエージェントが落ちても Mnemo 本体は巻き込まれず、Mnemo は MCP サーバーと同様に
再接続・再 spawn するだけで回復できなければならない。

```
Mnemo 本体 ──A2A──▶ サブエージェント ──MCP──▶ ツール群
（オーケストレータ）   （本規約の対象／登録制・遅延常駐・独立ランタイム）
```

---

## 1. 追加必須要件（MUST）— 被管理サブエージェント層

### S1. 登録可能であること（MCP と対称）
- Mnemo の**エージェントレジストリ**に登録して管理される。設定は MCP の `MCPServerConfig` と
  対称な `A2AAgentConfig`（`name` / `transport` / `command` / `url` / `builtin` / `enabled`）で表現される。
- **ビルトイン**サブエージェントは `python -m mnemo.agents.<name>.server` で stdio 起動できること。
- 外部サブエージェントは登録時に URL で接続できること。

### S2. ライフサイクル：遅延常駐（lazy-standing）に従う
- Mnemo は**初回タスク投入時に spawn** する（常時起動しない）。
- 起動後は**常駐サーバー**として、生存期間中に**複数タスクを順次受理**できること。1 タスクで自己終了しない。
- **アイドルおよび Mnemo からの終了要求で正常終了（graceful shutdown）**すること。
  終了時に進行中タスクがあれば、その状態を A2A 上で `failed`/`canceled` として確定してから落ちる。

### S3. 起動ハンドシェイク（stdio spawn 時）
- 起動時に**空きポートを自分で確保**し、待受開始後に **stdout へ 1 行の JSON** で接続先を通知する。
  - 暫定フォーマット（§5 で確定）:
    ```json
    {"a2a": "ready", "url": "http://127.0.0.1:<port>", "agent": "<name>", "version": "<x.y.z>"}
    ```
- ハンドシェイク行以外の診断ログは **stderr** に出す（stdout はハンドシェイク専用）。
- 前例: GUI の空きポート自動回避（ポート 8765 衝突時に空きポートへ退避）。同じ機構に倣う。

### S4. 隔離を破らない
- Mnemo 本体とメモリ・グローバル状態を共有しない。共有を前提とした実装をしてはならない。
- 自分のクラッシュが Mnemo 本体の再起動を要求してはならない（プロセス境界で隔離する）。
- 自分の作業ディレクトリ・一時ファイルは自分で管理し、後始末する。

### S5. 統一された管理インターフェースに対応する
Mnemo 本体の**単一 supervisor**が、全エージェントを同一手順で
**起動・停止・再起動・ゾンビ kill・ポート管理・バージョンチェック**できるよう、以下に対応する。

| 管理操作 | サブエージェント側に要る対応 |
|---|---|
| 起動 | ポートを stdout で返す（S3） |
| 停止 / 再起動 | graceful stop 要求に応答して安全に終了（S2）。応答が無い場合の強制 kill を許容 |
| ゾンビ kill | レジストリに記録される pid/port を持ち、後から識別・kill 可能（S3 と接続） |
| ポート管理 | 空きポートを自分で確保し報告（S3） |
| バージョンチェック | **稼働中の自分のバージョンを公開**（Agent Card または `/version` 相当） |

- **バージョン公開**: supervisor が導入版（バンドル/インストール版）と稼働版を比較できること。
- **強制 kill 耐性**: kill されても外部状態を壊さない（タスクは再投入され得る前提＝ §2 の冪等性）。

> supervisor・永続プロセスレジストリ・GUI 管理パネルは **Mnemo 本体側の実装**
> （[ASYNC_JOB_RESEARCH.md](ASYNC_JOB_RESEARCH.md) §7「エージェントプロセス管理」）。
> 本節は、それに管理される側として**サブエージェントが満たす義務**を定める。

> 完了 push（Part A I3）／完了ペイロード（Part A I4）／キャンセル（Part A I2）／
> MCP ツール（Part A I5）／Agent Card（Part A I6）／MNEMO_BASE_DIR（Part A I7）は Part A 参照。

---

## 2. 推奨（SHOULD）

- タスクは**冪等・再実行可能**に設計する（再起動復旧時に再投入され得る）。
- 重い初期化（モデルクライアント等）は起動時に一度だけ行い、タスク間で再利用する。
- 進捗は「割合」より「意味のあるログ行」を優先する。
- 長時間処理の途中で**チェックポイント**を残し、再開可能性を上げる。

---

## 3. テンプレート骨格（最小構成）

```text
src/mnemo/agents/<name>/
├── __init__.py
├── __main__.py        # python -m mnemo.agents.<name>.server 起動エントリ
├── server.py          # A2A サーバー構築・ポート確保・ハンドシェイク出力・常駐ループ
├── executor.py        # AgentExecutor 相当：タスク受領→実行→進捗SSE→完了push
└── card.py            # Agent Card 定義（name / capabilities / skills）
```

起動の擬似フロー（server.py）:

```text
1. 空きポート P を確保
2. a2a-python SDK で A2A サーバーを P で構築（executor / task store / push 通知ハンドラを登録）
3. 待受開始
4. stdout に {"a2a":"ready","url":"http://127.0.0.1:P",...} を 1 行出力（S3）
5. 常駐：タスクを受理し executor で処理。進捗は SSE、完了は push webhook（Part A I3）
6. アイドル timeout / 終了要求で graceful shutdown（S2）
```

---

## 4. ビルトインサブエージェントの初期対象（想定）

| name | 種別 | 性質 | 備考 |
|---|---|---|---|
| `deep_research` | ディープリサーチ | I/O バウンド（LLM＋Web） | 既存の deep-research 知見を独立ランタイムへ |
| `coding` | コーディング | subprocess 多用・長時間・暴走リスク | 隔離の価値が特に高い |

※ 対象と優先順位は実装仕様で確定する。

---

## 5. 未決事項（実装仕様で確定）

- ハンドシェイク JSON の最終フォーマット・タイムアウト（S3）
- アイドル自動終了の timeout 値と、終了判定の詳細（S2）
- 1 つの常駐サブエージェントにおける**タスク間の並行モデル**（直列 / プール）と相互隔離（S4 との整合）
- A2A SDK の TaskStore（ローカル）と Mnemo の `jobs` テーブル（正本）の役割分担
- graceful stop のタイムアウト値と強制 kill への移行条件（S5）
- バージョン公開の方式（Agent Card に載せる / `/version` を別途設ける）（S5）
- §5 横断的関心事（同時実行上限・結果ストア・再起動復旧・種別ごとタイムアウト, [ASYNC_JOB_RESEARCH.md](ASYNC_JOB_RESEARCH.md)）

---

## 出典

- Part A（共通インターフェース）: [A2A_INTERFACE_CONTRACT.md](A2A_INTERFACE_CONTRACT.md)
- A2A Protocol Specification: https://a2a-protocol.org/v0.2.5/specification/
- a2a-python（公式 Python SDK）: https://github.com/a2aproject/a2a-python
- 調査・方向性: [ASYNC_JOB_RESEARCH.md](ASYNC_JOB_RESEARCH.md)
