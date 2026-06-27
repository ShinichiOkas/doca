import os

# Ollama 接続情報
OLLAMA_HOST = os.environ.get("OLLAMA_HOST") or os.environ.get("DOCA_OLLAMA_URL") or "http://localhost:11434"

# 使用する LLM モデル
DOCA_MODEL = os.environ.get("DOCA_MODEL") or "qwen2.5-coder:7b"

# A2A サーバー設定
DEFAULT_PORT = int(os.environ.get("DOCA_A2A_PORT") or "8765")

# セキュリティのためのベースディレクトリ制限（カレントディレクトリをルートとする）
WORKSPACE_DIR = os.path.abspath(os.getcwd())
