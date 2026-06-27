import os
import sys
import subprocess
import platform
import shutil
from doca import config

def _secure_path(path: str) -> str:
    """
    対象パスを絶対パスに変換し、WORKSPACE_DIR配下にあるか確認する。
    配下にない場合は例外をスローする。
    """
    abs_path = os.path.abspath(os.path.join(config.WORKSPACE_DIR, path))
    if not abs_path.startswith(config.WORKSPACE_DIR):
        raise ValueError(f"Access Denied: Path '{path}' is outside the workspace '{config.WORKSPACE_DIR}'")
    return abs_path

def read_file(path: str) -> str:
    """指定されたファイルの内容を読み込む"""
    try:
        secure_path = _secure_path(path)
        if not os.path.exists(secure_path):
            return f"Error: File '{path}' does not exist."
        with open(secure_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {str(e)}"

def write_file(path: str, content: str) -> str:
    """指定されたファイルを作成または上書きする"""
    try:
        secure_path = _secure_path(path)
        os.makedirs(os.path.dirname(secure_path), exist_ok=True)
        with open(secure_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Success: File '{path}' has been written."
    except Exception as e:
        return f"Error writing file: {str(e)}"

def patch_file(path: str, target: str, replacement: str) -> str:
    """ファイルの一部を書き換える"""
    try:
        secure_path = _secure_path(path)
        if not os.path.exists(secure_path):
            return f"Error: File '{path}' does not exist."
        
        with open(secure_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        
        occurrences = content.count(target)
        if occurrences == 0:
            return f"Error: Target code block to replace was not found in '{path}'."
        elif occurrences > 1:
            return f"Error: Target code block is not unique. It matches {occurrences} places in '{path}'."
        
        new_content = content.replace(target, replacement, 1)
        with open(secure_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        return f"Success: File '{path}' has been patched."
    except Exception as e:
        return f"Error patching file: {str(e)}"

def delete_file(path: str) -> str:
    """指定されたファイルを削除する"""
    try:
        secure_path = _secure_path(path)
        if not os.path.exists(secure_path):
            return f"Error: File '{path}' does not exist."
        if os.path.isdir(secure_path):
            shutil.rmtree(secure_path)
            return f"Success: Directory '{path}' has been deleted."
        else:
            os.remove(secure_path)
            return f"Success: File '{path}' has been deleted."
    except Exception as e:
        return f"Error deleting file: {str(e)}"

def run_command(command: str) -> str:
    """シェルコマンドを実行し、出力を取得する（Windows 11ではPowerShellを使用）"""
    try:
        is_windows = platform.system() == "Windows"
        
        if is_windows:
            # Windows 11 / Windows では PowerShell をデフォルトとして実行
            # PowerShell を使うことで cmd.exe の制約や文字化けを回避しやすくする
            cmd_args = ["powershell", "-NoProfile", "-NonInteractive", "-Command", command]
        else:
            # UNIX系では通常のシェル経由で実行
            cmd_args = command
            
        result = subprocess.run(
            cmd_args,
            shell=not is_windows,  # Windowsではリスト形式の引数を使用するためshell=False、UNIXではshell=True
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,  # 30秒タイムアウト
            cwd=config.WORKSPACE_DIR
        )
        
        # 文字コード対策のデコード処理
        output_bytes = result.stdout + b"\n" + result.stderr
        output = ""
        for encoding in ["utf-8", "cp932", "shift_jis"]:
            try:
                output = output_bytes.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if not output:
            output = output_bytes.decode("utf-8", errors="replace")
            
        return f"Exit Code: {result.returncode}\n\nOutput:\n{output}"
    except subprocess.TimeoutExpired:
        return "Error: Command execution timed out (limit: 30 seconds)."
    except Exception as e:
        return f"Error executing command: {str(e)}"

# Ollama に渡すツールの定義リスト
TOOLS_DEFINITION = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the entire content of a file within the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path to the file from the workspace root."
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create a new file or overwrite an existing file with the specified content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path to the file to create or overwrite."
                    },
                    "content": {
                        "type": "string",
                        "description": "The exact file content to write."
                    }
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "patch_file",
            "description": "Partially replace a specific block of text in an existing file. This is highly recommended over write_file for editing files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path to the file to patch."
                    },
                    "target": {
                        "type": "string",
                        "description": "The exact block of text to be replaced. Must be unique within the file."
                    },
                    "replacement": {
                        "type": "string",
                        "description": "The new block of text to replace the target block."
                    }
                },
                "required": ["path", "target", "replacement"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Delete a file or directory within the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path to the file or directory to delete."
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Run a non-interactive shell command in the workspace. In Windows, this executes in PowerShell.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The command line string to execute."
                    }
                },
                "required": ["command"]
            }
        }
    }
]

# 関数マッピング
TOOLS_MAP = {
    "read_file": read_file,
    "write_file": write_file,
    "patch_file": patch_file,
    "delete_file": delete_file,
    "run_command": run_command
}
