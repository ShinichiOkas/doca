import os
import sys
import logging
from doca import config

# ログファイルパス
LOG_FILE = os.path.join(config.WORKSPACE_DIR, "doca.log")

# ロガーの作成
logger = logging.getLogger("doca")
logger.setLevel(logging.DEBUG)

# ログフォーマット定義
formatter = logging.Formatter(
    "[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# 1. ターミナル出力（stdoutを汚さないよう stderr に出力）
console_handler = logging.StreamHandler(sys.stderr)
console_handler.setLevel(logging.INFO)  # コンソールは INFO 以上
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# 2. ファイル出力（doca.log に詳細な DEBUG ログも記録）
file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
file_handler.setLevel(logging.DEBUG)  # ファイルは DEBUG 以上
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

def log_info(msg: str):
    logger.info(msg)

def log_debug(msg: str):
    logger.debug(msg)

def log_warning(msg: str):
    logger.warning(msg)

def log_error(msg: str, exc_info: bool = False):
    logger.error(msg, exc_info=exc_info)
