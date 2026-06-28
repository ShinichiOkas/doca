import os
import sys
import subprocess
import platform
import shutil
from doca import config

def _base_dir() -> str:
    """
    相対パスの解決基準ディレクトリ。
    親エージェントが作業ベース（config.WORK_BASE_DIR）を指定していればそれを、
    無ければ WORKSPACE_DIR を返す。
    """
    return config.WORK_BASE_DIR.get() or config.WORKSPACE_DIR

def _is_within(abs_path: str, root: str) -> bool:
    """
    abs_path が root ディレクトリ（root自身を含む）の配下にあるか判定する。
    os.path.commonpath を用いるため、文字列前方一致のような誤判定
    （例: 'doca' に対し 'doca-secret' を許可してしまう）を起こさない。
    """
    root = os.path.abspath(root)
    try:
        return os.path.commonpath([abs_path, root]) == root
    except ValueError:
        # ドライブが異なる等で共通パスが取れない場合は配下ではない
        return False

def _secure_path(path: str) -> str:
    """
    対象パスを絶対パスに変換し、許可ディレクトリ配下にあるか確認する。
    許可ディレクトリは WORKSPACE_DIR と、親エージェントから渡された
    追加許可パス（config.EXTRA_ALLOWED_PATHS）。
    いずれの配下にもない場合は例外をスローする。
    """
    abs_path = os.path.abspath(os.path.join(_base_dir(), path))
    allowed_roots = [config.WORKSPACE_DIR, _base_dir(), *config.EXTRA_ALLOWED_PATHS.get()]
    for root in allowed_roots:
        if _is_within(abs_path, root):
            return abs_path
    raise ValueError(
        f"Access Denied: Path '{path}' is outside the allowed workspace(s) {allowed_roots}"
    )

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
            cwd=_base_dir()
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
            "description": "Read the entire content of a file. Paths are resolved against the current working directory (the task's output folder).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file, normally a simple relative path such as 'main.py' or 'src/util.py'. It is resolved against the current working directory. Do NOT build an absolute path yourself; a plain relative path already points at the correct folder."
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
            "description": "Create or overwrite a file with the given content. The file is written under the current working directory, which is ALREADY the designated output folder for this task. Missing parent directories are created automatically.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Where to write, normally a simple relative path such as 'fibonacci.py' or 'docs/README.md'. It is created under the current working directory. Do NOT prepend an absolute base path (e.g. do not turn 'fibonacci.py' into 'C:/some/dir/fibonacci.py') — a plain relative path already lands in the correct output folder."
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
            "description": "Partially replace a specific block of text in an existing file. This is highly recommended over write_file for editing files. Paths are resolved against the current working directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to patch, normally a simple relative path resolved against the current working directory. Do NOT build an absolute path yourself."
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
            "description": "Delete a file or directory. Paths are resolved against the current working directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file or directory to delete, normally a simple relative path resolved against the current working directory. Do NOT build an absolute path yourself."
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
            "description": "Run a non-interactive shell command. The command runs with its working directory set to the current task's output folder (PowerShell on Windows). Because you are already inside that folder, use relative paths in commands (e.g. 'python fibonacci.py') rather than absolute paths.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The command line string to execute. Prefer relative paths; the command already runs inside the correct working/output directory."
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
