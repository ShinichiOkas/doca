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

# 親エージェントが指定した「作業ベースディレクトリ」。
# 設定されている場合、相対パスの解決基準と run_command の cwd を、
# WORKSPACE_DIR の代わりにこのディレクトリにする（タスク単位）。
# これにより、相対パス（例: 'out.py'）で書かれた成果物も指定フォルダ配下に格納される。
# 未設定（None）の場合は従来どおり WORKSPACE_DIR を基準とする。
WORK_BASE_DIR: ContextVar = ContextVar("WORK_BASE_DIR", default=None)
