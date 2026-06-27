# A2A エージェント・インターフェース規約（Mnemo エコシステム共通）

| 項目 | 内容 |
|---|---|
| 作成日 | 2026-06-16 |
| 最終更新 | 2026-06-24 |
| ステータス | 規約 v0.2（Mnemo クライアント＆AInote サーバー双方で動作検証済み。§I8 追加） |
| 適用対象 | Mnemo エコシステムに参加する**すべての A2A エージェント** |
| 位置づけ | normative（必ず守るべきルール）。Part A = 共通インターフェース層 |
| 関連 | Part B = [A2A_SUBAGENT_CONTRACT.md](A2A_SUBAGENT_CONTRACT.md)（被管理サブエージェントの追加義務）／根拠 = [ASYNC_JOB_RESEARCH.md](ASYNC_JOB_RESEARCH.md) §7 |

> **2 層構成**：
> - **Part A（本書）= A2A インターフェース層**。プロトコル表面の共通規約。**Mnemo 本体も A2A サーバーとしてこれに準拠する**。
> - **Part B = 被管理サブエージェント層**。Mnemo が spawn・管理する子プロセスだけの追加義務（登録・遅延常駐・ハンドシェイク・隔離）。
>
> Mnemo が管理する子サブエージェントは **Part A ＋ Part B の両方**を満たす。
> Mnemo 本体や外部の対向エージェントは **Part A のみ**を満たす。

---

## 0. 適用対象

| 主体 | Part A | Part B |
|---|---|---|
| Mnemo 本体（A2A サーバーとして自分の能力を公開） | ✅ 準拠 | — （ホストであり被管理の子ではない） |
| Mnemo が spawn・管理する子サブエージェント（deep_research / coding 等） | ✅ 準拠 | ✅ 準拠 |
| 外部の対向 A2A エージェント | ✅ 準拠 | — |

Mnemo は **A2A クライアント（子へタスク投入）兼 A2A サーバー（自分の能力を公開）**になる。
本規約に準拠することで、Mnemo 自身が規約の参照実装（ドッグフーディング）となる。

---

## 1. エコシステム全体像

```
            ┌────────────── A2A ──────────────┐
            ▼                                  ▼
 外部オーケストレータ            Mnemo 本体  ──A2A──▶ サブエージェント ──MCP──▶ ツール群
 ／別エージェント ──A2A──▶  （クライアント兼サーバー）  （Part A＋B）
                            （Part A 準拠）
```

- A2A（エージェント間）と MCP（エージェント↔ツール）は補完関係。
- Mnemo は既に MCP ホスト。A2A サーバー面を足しても自然に積める。

---

## 2. 必須要件（MUST）— インターフェース層

### I1. A2A プロトコル準拠
- 公式 **a2a-python SDK**（spec 1.0）を用いて **A2A サーバー**として振る舞う。
- Mnemo 本体は FastAPI（Starlette ベース）上に A2A SDK の ASGI アプリをマウントして公開する。独自プロトコルで代替しない。
- v0.3 互換レイヤー（`enable_v0_3_compat`）はデフォルト無効。原則 v1.0 のみサポートする。

### I2. タスクライフサイクルとキャンセル
- A2A の **task 状態**（submitted → working → completed / failed / canceled …）を正しく実装し、遷移を報告する。
- 対向からの**キャンセル要求に応答**できること（協調的キャンセルを最低限サポート）。

### I3. 進捗ストリームと完了通知
- 接続中は **A2A の SSE で進捗を逐次配信**する（長時間タスクでは意味のある進捗があること）。
- 完了（成功・失敗）は、タスク投入時に渡される **push 通知設定（webhook URL）へ HTTP POST** して確定する。
  接続が切れていても完了を取りこぼさせない。

### I4. 完了ペイロードに「相手が次に動くための情報」を含める
- 最終 artifact / status に以下を含める：
  - 簡潔な件名/要約（`subject` 相当）
  - 成功/失敗の別
  - 成果物への参照（巨大な成果物は本文に詰めず、ファイル/ID 参照で返す）

### I5. ツールアクセスは MCP を使う
- 外部ツール/データへのアクセスは **MCP** を介する（A2A↔MCP は補完）。

### I6. Agent Card を公開する
- 名前・能力（capabilities）・提供スキル（skills）を含む **Agent Card** を A2A 仕様に従って公開する。
- **正しいパス**: `{base_url}/.well-known/agent-card.json`（a2a-python SDK のデフォルト）。
  - ⚠️ `agent.json` は**誤り**。旧仕様・他実装で使われているが a2a-python SDK は `agent-card.json` しか公開しない。
- ローカル登録制のため探索の重い部分は簡略化してよい。

### I7. base_dir は環境変数を直接参照する（Mnemo 同梱実装の場合）
- Mnemo 本体および Mnemo 同梱のビルトインエージェントは、`CLAUDE.md`「MNEMO_BASE_DIR — 絶対的ルール」に従う。
- `main.py` が起動時に確定した `$env:MNEMO_BASE_DIR` を**そのまま参照**する。自前フォールバック分岐を書かない。
- （外部の対向エージェントには適用されない）

### I8. v1.0 JSON-RPC の具体的な呼び出し形式（実装確認済み）

a2a-python SDK v1.0 の JSON-RPC エンドポイントは **gRPC スタイルのメソッド名**を使用する（v0.3 の `tasks/send` / `message/send` ではない）。Mnemo クライアント（`a2a_client.py`）と AInote サーバーの両方で動作確認済み。

**エンドポイント規約:**

| 項目 | 値 |
|---|---|
| JSON-RPC パス | `{登録URL}`（慣例として `{base_url}/rpc`） |
| Agent Card パス | `{base_url}/.well-known/agent-card.json`（※ `agent.json` は誤り） |
| 必須ヘッダー | `A2A-Version: 1.0` |

**タスク投入（SendMessage）:**

```json
{
  "jsonrpc": "2.0",
  "id": "<uuid>",
  "method": "SendMessage",
  "params": {
    "message": {
      "messageId": "<uuid>",
      "role": "ROLE_USER",
      "parts": [{"text": "タスク内容"}],
      "contextId": "<session-id>"
    }
  }
}
```

レスポンス:
```json
{
  "result": {
    "task": {
      "id": "<server-generated-id>",
      "status": {"state": "TASK_STATE_COMPLETED"}
    }
  }
}
```

タスク ID はサーバーが生成する。`state` は `TASK_STATE_SUBMITTED` / `TASK_STATE_WORKING` / `TASK_STATE_COMPLETED` / `TASK_STATE_FAILED` など。

**タスク状態取得（GetTask）:**

```json
{"jsonrpc": "2.0", "id": "<uuid>", "method": "GetTask", "params": {"id": "<task-id>"}}
```

**タスクキャンセル（CancelTask）:**

```json
{"jsonrpc": "2.0", "id": "<uuid>", "method": "CancelTask", "params": {"id": "<task-id>"}}
```

> **注意**: v0.3 互換モード（`enable_v0_3_compat=True`）では `message/send`, `tasks/get`, `tasks/cancel` が使えるが、デフォルト（`False`）では使えない。互換モードを有効にしない限り v1.0 の gRPC スタイルで呼ぶこと。

---

## 3. 完了通知の接続（Mnemo がクライアントのとき）

Mnemo が対向（サブエージェント）にタスクを投入した場合、その完了 push は Mnemo 本体が受信し、
ユーザー通知（ベル）へ接続される：

```
対向エージェント完了
  → A2A push 通知（webhook=HTTP POST）を Mnemo 本体が受信
  → emit_system_notification(...)        ← 実装済み（core/notification.py）
  → EventSource.system のイベントとして永続化＋SSEでベルへ
```

完了通知の「受け口」は既存（スケジュール実行通知で導入済み、LONGTERM_TODO の SN セクション）。

---

## 4. 未決事項（実装仕様で確定）

- キャンセルの強度（協調的のみ / 強制フォールバック）（I2）
- A2A SDK の TaskStore と Mnemo の `jobs` テーブル（正本）の役割分担（Part B と跨る）
- Mnemo 自身の A2A サーバー面（外部から Mnemo をエージェントとして呼ぶ方向）の実装（I1）

---

## 出典

- A2A Protocol Specification: https://a2a-protocol.org/v0.2.5/specification/
- Streaming & Asynchronous Operations: https://a2a-protocol.org/latest/topics/streaming-and-async/
- a2a-python（公式 Python SDK）: https://github.com/a2aproject/a2a-python
- A2A and MCP（補完関係）: https://a2a-protocol.org/latest/topics/a2a-and-mcp/
- 調査・方向性: [ASYNC_JOB_RESEARCH.md](ASYNC_JOB_RESEARCH.md)
