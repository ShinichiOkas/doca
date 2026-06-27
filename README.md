# Doca: Ollama-powered Minimal Coding Agent

Doca（ドカ）は、ローカルLLMサーバー（Ollama）をバックエンドとして使用する、ミニマルかつ強力なコーディングエージェントです。Pythonで実装されており、PyInstallerを使用して単一の実行ファイル（onefile exe）としてビルドできます。パスの通った場所にexeを置くだけで、複雑な環境構築なしですぐに動作します。

本エージェントは、コマンドライン（CLI）、対話型（REPL）、およびFastAPIベースのA2A（Agent-to-Agent）の3つのインターフェースを提供します。A2Aインターフェースは、Mnemoエコシステム共通のA2A規約（Part A & Part B）に準拠しており、他エージェントの被管理サブエージェント（`coding`等）として遅延起動・常駐させることができます。

---

## 🚀 主な特徴

1. **ポータブルなシングルバイナリ (Onefile Exe)**
   - PyInstallerにより、すべての依存関係を1つの `.exe` ファイルにパッケージング可能。パスを通すだけでどこでも動作します。
   - **バイナリサイズ削減のため、依存パッケージは最小限に抑える設計**にしています（詳細は下記「設計方針」を参照）。
2. **ローカルLLM (Ollama) 専用設計**
   - ローカル環境で動作するOllamaのLLMモデル（例：`qwen2.5-coder`, `llama3` など）を利用し、プライバシーとセキュリティを守りながらコーディングを自動化します。
3. **3つのユーザーインターフェース**
   - **CLI モード**: 単発の指示をコマンド引数で渡し、非対話的にタスクを処理。
   - **REPL モード**: ターミナル上でエージェントと対話しながら段階的にコーディングを進行。
   - **A2A モード**: FastAPIを使用したサーバーを起動し、他のオーケストレータや親エージェント（Mnemoなど）からのJSON-RPCタスク指示を受理。
4. **自律的なファイル操作とコマンド実行**
   - ファイルの読み書き、部分書き換え（パッチ適用）、ファイルの作成・削除、およびローカルコマンド実行のツールをLLMに提供。LLM自身がコードを書き、テストを実行して自己修正するループを構築します。

---

## 💡 設計方針（軽量性の維持）

PyInstallerによるワンファイル `.exe` ビルド時のファイルサイズを極力小さく（実用的な数十MB程度に）抑えるため、以下の設計方針を徹底しています。

- **大容量外部パッケージの排除**:
  - `numpy`, `pandas`, `scipy` などの数値計算系ライブラリや、重い機械学習フレームワークは一切インポートしません。
- **Ollama APIの直接呼び出し**:
  - 重い依存関係を伴う Ollama 公式 Python SDK などのラッパーは使用せず、Python標準の `urllib.request` や、極めて軽量な HTTP クライアント（`httpx` や `requests` など最小限のもの）のみを用いて Ollama の REST API (`/api/generate` や `/api/chat`) を直接叩きます。
- **フレームワークの厳選**:
  - A2Aインターフェース用のWebサーバーには `FastAPI` + `Uvicorn` を使用しますが、それ以外の重い Web / ユーティリティフレームワークは導入せず、標準ライブラリ（`subprocess`, `json`, `os`, `sys` など）を最大限に活用します。

---

## 📁 プロジェクト構成

```text
doca/
├── doc/
│   ├── A2A_INTERFACE_CONTRACT.md   # A2A共通インターフェース規約 (Part A)
│   └── A2A_SUBAGENT_CONTRACT.md    # 被管理サブエージェント規約 (Part B)
├── src/
│   └── doca/
│       ├── __init__.py
│       ├── __main__.py             # エントリポイント
│       ├── cli.py                  # CLIインターフェースの実装
│       ├── repl.py                 # REPL対話型インターフェースの実装
│       ├── server.py               # A2A FastAPIサーバー・ハンドシェイク・常駐ループ
│       ├── agent.py                # LLM (Ollama) との連携および思考ループ
│       ├── tools.py                # ファイル操作・コマンド実行ツールの定義
│       └── config.py               # 設定管理（Ollama URL、モデル名等）
├── README.md                       # 本ファイル
└── pyproject.toml / requirements.txt
```

---

## 🛠 動作要件

- **Python 3.10以上** (開発・ビルド時)
- **Ollama** がローカルで稼働していること
  - 推奨モデル: `qwen2.5-coder:7b` もしくはそれ以上のコーディング特化モデル

---

## 💻 使い方

### 1. 準備

Ollamaでコーディング向けモデルをプルしておきます。

```bash
ollama pull qwen2.5-coder:7b
```

環境変数でOllamaの接続先や使用モデルをカスタマイズできます。

```bash
# Windows (PowerShell)
$env:OLLAMA_HOST = "http://localhost:11434"
$env:DOCA_MODEL = "qwen2.5-coder:7b"
```

### 2. REPLモード (対話型)
ターミナル上で直接エージェントと対話しながら作業を進めます。

```bash
python -m doca
# またはビルド済みexeを実行
doca.exe
```

### 3. CLIモード (単発実行)
1行の指示でタスクを処理させます。

```bash
python -m doca.cli --task "src/utils.py のバグを修正して pytest を実行してください"
# または
doca.exe --task "src/utils.py のバグを修正して pytest を実行してください"
```

### 4. A2Aモード (エージェント間連携)
FastAPIによるA2Aサーバーを起動します。Mnemoなどの親エージェントによってサブプロセスとして呼び出される（stdio spawn）場合、規約に基づき自動的に空きポートを確保し、stdoutに準備完了JSONを出力して遅延常駐します。

```bash
python -m doca.server
# または
doca.exe --a2a
```

---

## 🔌 A2A仕様への準拠内容

Docaは以下のA2A規約に完全準拠しています。

### 起動ハンドシェイク (Part B §S3)
stdio経由で親プロセスに起動された際、自律的に利用可能な空きポートを検索し、FastAPIを起動します。起動完了後、`stdout` に以下のJSONを1行だけ出力します。これにより、親プロセスは動的にポートを検知してA2A API経由でタスクを投入できます。

```json
{"a2a": "ready", "url": "http://127.0.0.1:<port>", "agent": "doca", "version": "0.1.0"}
```
*(ハンドシェイク以外のログやデバッグ出力はすべて `stderr` に出力されます)*

### APIエンドポイント
A2A v1.0のJSON-RPC仕様に従い、以下のエンドポイントを提供します。

- **JSON-RPC エンドポイント**: `/rpc`
  - `SendMessage`: タスクの投入（状態は `TASK_STATE_SUBMITTED` / `TASK_STATE_WORKING` 等で遷移）
  - `GetTask`: タスク状態の取得
  - `CancelTask`: 進行中タスクの協調的キャンセル
- **Agent Card**: `/.well-known/agent-card.json`
  - 提供するツール（Capabilities）やエージェント情報の開示。

---

## 🔨 ビルト方法 (Onefile Exe)

PyInstallerを使用して、依存ライブラリやFastAPI、Uvicornを内包した単一の実行ファイルをビルドします。

```bash
# 依存関係のインストール
pip install -r requirements.txt
pip install pyinstaller

# exeのビルド (dist/doca.exe が生成されます)
pyinstaller --onefile --name doca src/doca/__main__.py
```

生成された `dist/doca.exe` を `C:\Users\<User>\bin` などの環境変数 `PATH` が通ったディレクトリにコピーするだけで、どこからでも `doca` コマンドが利用可能になります。

---

## 📝 ライセンス
[MIT License](LICENSE)
