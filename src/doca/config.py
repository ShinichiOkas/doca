import os
from contextvars import ContextVar

# Ollama 接続情報
OLLAMA_HOST = os.environ.get("OLLAMA_HOST") or os.environ.get("DOCA_OLLAMA_URL") or "http://localhost:11434"

# 使用する LLM モデル
DOCA_MODEL = os.environ.get("DOCA_MODEL") or "qwen2.5-coder:7b"

# A2A サーバー設定
DEFAULT_PORT = int(os.environ.get("DOCA_A2A_PORT") or "8780")

# セキュリティのためのベースディレクトリ制限（カレントディレクトリをルートとする）
WORKSPACE_DIR = os.path.abspath(os.getcwd())

# 親エージェントから渡される追加の書き込み許可パス。
# WORKSPACE_DIR に加えて、ここに登録されたディレクトリ配下も読み書きを許可する。
# 並行タスクが互いの許可設定に干渉しないよう、タスク（実行コンテキスト）単位で
# 分離するために ContextVar を用いる（グローバル変数だと並行実行時に混線する）。
EXTRA_ALLOWED_PATHS: ContextVar = ContextVar("EXTRA_ALLOWED_PATHS", default=())
