import sys
from doca import agent
from doca import config

def print_help():
    print("""
Doca REPL モード - コマンド一覧:
  /help               : このヘルプを表示します。
  /exit, /quit        : REPLを終了します。
  /reset              : 会話履歴（コンテキスト）をリセットします。
  /model <モデル名>    : 使用するOllamaモデルを変更します（例: /model llama3）。
  ※コマンド以外の入力はすべてエージェントへの指示として処理されます。
""")

def run_repl():
    """
    対話型REPLモードを実行する。
    """
    print(f"=== Doca REPL モード (モデル: {config.DOCA_MODEL}) ===")
    print("ヘルプを表示するには '/help'、終了するには '/exit' を入力してください。")
    print(f"ワークスペース: {config.WORKSPACE_DIR}\n")
    
    history = []
    
    # 進捗表示用コールバック
    def progress_callback(msg: str, percent: int):
        # 1行で進捗を上書き表示する（キャリッジリターン \r を使用）
        sys.stdout.write(f"\r\033[K[{percent}%] {msg}")
        sys.stdout.flush()

    while True:
        try:
            user_input = input("doca> ").strip()
            if not user_input:
                continue
            
            # メタコマンドの処理
            if user_input.startswith("/"):
                parts = user_input.split(maxsplit=1)
                cmd = parts[0].lower()
                
                if cmd in ["/exit", "/quit"]:
                    print("Doca REPL を終了します。")
                    break
                elif cmd == "/help":
                    print_help()
                elif cmd == "/reset":
                    history.clear()
                    print("会話履歴をリセットしました。")
                elif cmd == "/model":
                    if len(parts) < 2:
                        print(f"現在のモデル: {config.DOCA_MODEL}")
                    else:
                        new_model = parts[1].strip()
                        config.DOCA_MODEL = new_model
                        print(f"モデルを '{new_model}' に変更しました。")
                else:
                    print(f"未知のコマンドです: {cmd} (ヘルプは /help)")
                continue
            
            # エージェントによるタスクの実行
            sys.stdout.write("[0%] 準備中...")
            sys.stdout.flush()
            
            result = agent.run_agent_loop(user_input, on_progress=progress_callback, history=history)
            
            # 進捗表示の行をクリアして最終結果を表示
            sys.stdout.write("\r\033[K")
            sys.stdout.flush()
            
            print(result)
            print("-" * 50)
            
        except KeyboardInterrupt:
            # Ctrl+Cで入力をキャンセル
            print("\n入力がキャンセルされました。終了するには /exit を入力してください。")
        except EOFError:
            # Ctrl+Dやリダイレクト終了時
            print("\n終了します。")
            break
        except Exception as e:
            print(f"\nエラーが発生しました: {str(e)}")
