import argparse
import sys
from doca import config
from doca import cli
from doca import repl
from doca import server

def main():
    parser = argparse.ArgumentParser(
        description="Doca: Ollama-powered Minimal Coding Agent"
    )
    
    # 動作モード切替
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "-t", "--task",
        type=str,
        help="CLIモードで実行する単発タスクの指示"
    )
    group.add_argument(
        "--a2a",
        action="store_true",
        help="FastAPIサーバーを起動してA2A（Agent-to-Agent）モードで動作する"
    )
    
    # 共通オプション
    parser.add_argument(
        "-m", "--model",
        type=str,
        help=f"使用するOllamaモデル名 (デフォルト: {config.DOCA_MODEL})"
    )
    parser.add_argument(
        "-u", "--ollama-url",
        type=str,
        help=f"Ollamaサーバーの接続先URL (デフォルト: {config.OLLAMA_HOST})"
    )
    
    args = parser.parse_args()
    
    # オプション値の上書き反映
    if args.model:
        config.DOCA_MODEL = args.model
    if args.ollama_url:
        config.OLLAMA_HOST = args.ollama_url

    # 動作モードの分岐
    if args.task:
        # CLI モード
        cli.run_cli(args.task)
    elif args.a2a:
        # A2A (FastAPI) モード
        server.run_server()
    else:
        # REPL モード (デフォルト)
        repl.run_repl()

if __name__ == "__main__":
    main()
