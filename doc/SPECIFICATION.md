# Doca 外部・内部設計仕様書

Doca（ドカ）は、ローカルLLMサーバー（Ollama）をバックエンドとして使用する、ミニマルかつポータブルなコーディングエージェントです。本ドキュメントは、Docaの動作仕様、インターフェース仕様、ツール仕様、および実装・ビルドに関する設計を定義します。

---

## 1. システム構成・アーキテクチャ

Docaは以下のコンポーネントで構成されます。外部ライブラリを最小限に抑え、PyInstallerでのビルドサイズを軽量化するため、Pythonの標準ライブラリを最大限活用します。

```
                    ┌─────────────────────────┐
                    │       ユーザー /        │
                    │   親エージェント(Mnemo)  │
                    └────────────┬────────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         │ (1) CLI               │ (2) REPL              │ (3) A2A (FastAPI)
         ▼                       ▼                       ▼
┌────────────────────────────────────────────────────────────────────────┐
│                              Doca コア                                 │
│  - 思考ループ (Reasoning Loop)                                        │
│  - プロンプト管理 (System Prompt / Context)                           │
│  - Ollama クライアント (HTTP API 連携)                                  │
└────────────────────────┬───────────────────────────────────────────────┘
                         │ ツール呼び出し (Tool Calling)
                         ▼
┌────────────────────────────────────────────────────────────────────────┐
│                              ツールセット                              │
│  - read_file    - write_file    - patch_file                           │
│  - delete_file  - run_command                                          │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. インターフェース仕様

Docaは起動引数に応じて、3つの動作モード（CLI、REPL、A2A）を切り替えます。

### 2.1. CLI モード

コマンドライン引数で受け取ったタスクを即時に実行し、終了コードを返します。

- **起動コマンド例**:
  ```bash
  doca.exe --task "src/utils.py のリファクタリング" [--model "qwen2.5-coder:7b"] [--ollama-url "http://localhost:11434"]
  ```
- **引数仕様**:
  - `-t`, `--task` (str): 実行するタスク内容。指定された場合、CLIモードで動作。
  - `-m`, `--model` (str): 使用するOllamaモデル名（省略時は `DOCA_MODEL` 環境変数、またはデフォルトの `qwen2.5-coder:7b`）。
  - `-u`, `--ollama-url` (str): Ollamaの接続先（省略時は `OLLAMA_HOST` 環境変数、またはデフォルトの `http://localhost:11434`）。
- **出力規約**:
  - 進捗ログや思考プロセスは標準エラー出力 (`stderr`) に出力します。
  - 最終的な成果物のサマリーや成功メッセージは標準出力 (`stdout`) に出力します。
- **終了コード**:
  - `0`: タスク正常終了。
  - `1`: エラー終了（Ollama接続失敗、ツール実行時エラー、あるいはLLMがタスク失敗と判断した場合）。

---

### 2.2. REPL モード

対話型のインターフェースを提供し、ユーザーと対話しながら段階的にコーディングを実行します。

- **起動コマンド例**:
  ```bash
  doca.exe
  ```
- **仕様**:
  - プロンプト表示: `doca> `
  - **Windows 11互換性と軽量化設計**:
    - Python標準の `readline` ライブラリはWindows環境ではデフォルトで提供されていません。バイナリサイズ削減のため、`pyreadline3` などの外部依存ライブラリは導入せず、標準の `input()` を用いたシンプルなループを基本とし、履歴や補完機能は最小限に抑えるか、標準機能の範囲内で実装します。
  - **メタコマンド**:
    - `/exit`, `/quit`: エージェントを終了します。
    - `/help`: ヘルプを表示します。
    - `/reset`: これまでの会話文脈（コンテキスト）を初期化します。
    - `/model <model_name>`: 動的にモデルを切り替えます。

---

### 2.3. A2A（Agent-to-Agent）モード

FastAPIを使用したWebサーバーとして動作し、親エージェントからのJSON-RPCタスク指示を受理します。Mnemoエコシステム規約（[A2A_INTERFACE_CONTRACT.md](A2A_INTERFACE_CONTRACT.md), [A2A_SUBAGENT_CONTRACT.md](A2A_SUBAGENT_CONTRACT.md)）に完全準拠します。

- **Windows 11における注意点**:
  - 親プロセス（Mnemo本体等）から stdio 経由で spawn された際、Windowsの環境変数 `PATH` やファイルパスのデリミタ（バックスラッシュ `\`）を適切にハンドリングします。

- **起動コマンド例**:
  ```bash
  doca.exe --a2a
  ```

#### 2.3.1. 起動ハンドシェイク（stdio spawn 時）
1. 起動時に、利用可能な空きポート（デフォルト: `8780` から開始してインクリメント）を検索し、ソケットを確保します。
2. 待受（FastAPIサーバーの起動）完了後、`stdout` に以下のJSON（1行）のみを出力します。
   ```json
   {"a2a": "ready", "url": "http://127.0.0.1:<port>", "agent": "doca", "version": "0.1.0"}
   ```
3. ハンドシェイク行以外の診断ログやアクセスログはすべて `stderr` に出力します。

#### 2.3.2. JSON-RPC v1.0 エンドポイント（`/rpc`）
以下のメソッドをサポートします。

- **`SendMessage`**: タスクの投入
  - リクエスト例:
    ```json
    {
      "jsonrpc": "2.0",
      "id": "req-001",
      "method": "SendMessage",
      "params": {
        "message": {
          "messageId": "msg-001",
          "role": "ROLE_USER",
          "parts": [{"text": "src/main.py にハローワールドを追加して"}],
          "contextId": "session-001"
        }
      }
    }
    ```
  - レスポンス例:
    ```json
    {
      "jsonrpc": "2.0",
      "id": "req-001",
      "result": {
        "task": {
          "id": "task-abc-123",
          "status": {"state": "TASK_STATE_WORKING"}
        }
      }
    }
    ```
  - **`params.configuration`（任意）**: 親エージェントからタスク単位の設定を渡します。
    - `pushNotificationConfig.url` (str): 完了時の Webhook 通知先 URL。
    - `workspacePaths` (str[]): **このタスクに限り、ワークスペース（実行時ディレクトリ）に加えて読み書きを許可する追加ディレクトリのリスト。** 親エージェントが指定した協働フォルダ（Coworkingフォルダ等）を doca のサンドボックス外であっても書き込み可能にするための仕組みです。指定された各ディレクトリ配下のみが許可対象で、前方一致による誤許可は行いません（`os.path.commonpath` による厳密判定）。タスクごとに分離され、他タスクの許可設定には影響しません。
    - リクエスト例（協働フォルダを許可する場合）:
      ```json
      {
        "method": "SendMessage",
        "params": {
          "message": {
            "parts": [{"text": "成果物を S:/work/develop/temp に格納してください"}]
          },
          "configuration": {
            "workspacePaths": ["S:/work/develop/temp"]
          }
        }
      }
      ```
    - 注意: `workspacePaths` はサンドボックスの許可リストを拡張するだけです。エージェントが実際にその場所へ書き込むためには、書き込み先パスをタスク本文（`message.parts[].text`）にも明示する必要があります。

- **`GetTask`**: タスク状態の取得
  - パラメータ: `{"id": "<task-id>"}`
  - レスポンス: タスクの現在の状態（`TASK_STATE_COMPLETED` / `TASK_STATE_FAILED` など）と結果ペイロード。

- **`CancelTask`**: 進行中タスクの協調的キャンセル
  - パラメータ: `{"id": "<task-id>"}`

#### 2.3.3. SSE (Server-Sent Events) による進捗配信
A2Aサーバーは、タスクの進捗状況をSSEストリームでリアルタイム配信します。
- イベントタイプ: `progress`
- データ構造: `{"message": "思考中...", "percentage": 50}` のように、進捗メッセージと進捗率（任意）を含みます。

#### 2.3.4. Agent Card（`/.well-known/agent-card.json`）
エージェントのプロフィールと提供ツール（capabilities / skills）を定義したJSONを返します。
- `capabilities.tools` (bool): ツール呼び出し対応。
- `capabilities.workspacePaths` (bool): `SendMessage` の `params.configuration.workspacePaths` による追加許可ディレクトリ指定に対応していることを示します（[2.3.2](#232-json-rpc-v10-エンドポイントrpc) 参照）。

---

## 3. ツール仕様 (Tool Calling)

エージェントが使用するツールは、Ollamaのツール呼び出し（Function Calling）機能、またはシステムプロンプトによるテキストパース（ReAct形式）を用いてLLMに公開されます。

### 3.1. `read_file`
指定されたファイルの内容を読み込みます。

- **引数**:
  - `path` (str): 読み込むファイルの相対・絶対パス。
- **動作制限**:
  - ディレクトリトラバーサル防止のため、原則としてエージェント実行時ディレクトリ配下（ワークスペース内）のファイルに限定します。
  - ただし、`SendMessage` の `params.configuration.workspacePaths` で親エージェントから渡された追加許可ディレクトリ配下も、当該タスクに限り読み書き可能です（[2.3.2](#232-json-rpc-v10-エンドポイントrpc) 参照）。許可判定は `os.path.commonpath` による厳密な配下チェックで行い、文字列前方一致による誤許可は発生しません。

### 3.2. `write_file`
指定されたファイルを作成し、または上書きします。

- **引数**:
  - `path` (str): 対象ファイルのパス。
  - `content` (str): 書き込む内容。
- **動作制限**:
  - 新規作成時、必要な親ディレクトリは自動的に作成します。

### 3.3. `patch_file`
ファイルの一部を書き換えます（差分適用）。巨大なファイルの全上書きを避け、効率的に修正を行うための必須ツールです。

- **引数**:
  - `path` (str): 対象ファイルのパス。
  - `target` (str): 置換したい既存のコードブロック（完全一致）。
  - `replacement` (str): 置換後のコードブロック。
- **動作**:
  - `target` がファイル内で一意に特定できる場合のみ置換を実行します。複数マッチした場合や、マッチしない場合はエラーを返します。

### 3.4. `delete_file`
指定されたファイルを削除します。

- **引数**:
  - `path` (str): 削除対象ファイルのパス。

### 3.5. `run_command`
コマンドラインで任意のシェルコマンドを実行します。

- **引数**:
  - `command` (str): 実行するコマンド文字列。
- **動作仕様**:
  - コマンドはサブプロセス (`subprocess.run`) を使用して実行されます。
  - **Windows 11におけるデフォルトシェル（PowerShell）**: 
    - 実行環境がWindows 11の場合、デフォルトの実行シェルとして **PowerShell (`powershell.exe`)** を使用します（例: `subprocess.run(["powershell", "-Command", command], ...)`）。
    - これにより、cmd.exeの制限を回避し、一貫したコマンド実行環境を提供します。Windows以外のOSでは、システムのデフォルトシェルを使用します。
  - **Windows 11における文字コード対策**: Windows環境では実行するコマンドによって出力される文字コードが CP932 (Shift_JIS) または UTF-8 になるため、デコード時には `errors="replace"` を指定するか、複数のエンコーディング（`utf-8`, `cp932` 等）をフォールバックとして順に試すことで、デコードエラーによるエージェントのクラッシュを防止します。
  - 標準出力 (`stdout`) と標準エラー出力 (`stderr`) の両方をマージしてエージェントにフィードバックします。
  - **セキュリティ制限**: 長時間稼働するコマンド（無限ループなど）や対話型の入力を求めるコマンドはタイムアウト（デフォルト: 30秒）で強制終了させます。

---

## 4. Ollama 連携仕様

Docaは外部APIキーを使用せず、ローカルのOllamaインスタンスと直接REST通信を行います。

- **エンドポイント**: `POST {ollama_url}/api/chat`
- **通信ライブラリ**: PyInstallerビルドサイズ削減のため、Python標準の `urllib.request` を使用して以下のように接続します。
  ```python
  import urllib.request
  import json

  def call_ollama(api_url, model, messages, tools=None):
      payload = {
          "model": model,
          "messages": messages,
          "stream": False,
          "options": {
              "temperature": 0.2  # コーディング向けに低めの値に設定
          }
      }
      if tools:
          payload["tools"] = tools

      req = urllib.request.Request(
          f"{api_url}/api/chat",
          data=json.dumps(payload).encode("utf-8"),
          headers={"Content-Type": "application/json"}
      )
      
      with urllib.request.urlopen(req) as res:
          return json.loads(res.read().decode("utf-8"))
  ```
- **フォールバック**: 使用しているOllamaのモデルがFunction Calling（ツール呼び出し）をサポートしていない場合、システムプロンプトを通じて XMLタグ または JSONブロック（ReActプロンプト）で思考とツール呼び出しをテキスト出力させ、Docaコアがそれをパースして実行します。

---

## 5. パッケージング・軽量化仕様 (PyInstaller)

PyInstallerによるビルド時にexeサイズが肥大化するのを防ぐため、以下の措置を講じます。

1. **除外パッケージ (Excludes)**:
   - ビルドコマンド実行時、暗黙的に読み込まれる不要なパッケージ（`numpy`, `pandas`, `matplotlib`, `scipy` 等）を明示的に除外します。
2. **ビルドコマンド**:
   ```bash
   pyinstaller --onefile \
               --name doca \
               --exclude-module numpy \
               --exclude-module pandas \
               --exclude-module matplotlib \
               --exclude-module tkinter \
               src/doca/__main__.py
   ```
3. **成果物**:
   - 生成されるバイナリ `doca.exe` は、FastAPI/Uvicorn/標準ライブラリを内包し、ファイルサイズは約20〜30MB程度を目指します。
