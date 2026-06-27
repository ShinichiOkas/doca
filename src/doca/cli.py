import sys
from doca import agent

def run_cli(task: str):
    """
    CLIモードでタスクを実行する。
    進捗ログは stderr に、最終的な回答は stdout に出力する。
    """
    def progress_callback(msg: str, percent: int):
        sys.stderr.write(f"[{percent}%] {msg}\n")
        sys.stderr.flush()

    sys.stderr.write(f"タスクを開始します: {task}\n")
    sys.stderr.flush()
    
    try:
        result = agent.run_agent_loop(task, on_progress=progress_callback)
        sys.stderr.write("タスクが終了しました。\n\n")
        sys.stderr.flush()
        
        # 最終回答を stdout に出力
        print(result)
        sys.exit(0)
    except Exception as e:
        sys.stderr.write(f"エラーが発生しました: {str(e)}\n")
        sys.stderr.flush()
        sys.exit(1)
