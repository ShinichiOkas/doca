import os
import urllib.request
import json
import traceback
import re
from typing import Callable, List, Dict, Any, Optional
from doca import config
from doca import tools
from doca import logger

SYSTEM_PROMPT = """You are Doca, a minimal and powerful agentic coding assistant.
You can read, write, patch, and delete files in the workspace, and run command line tools to verify your changes.
You are running in a Windows 11 environment. The default command execution shell is PowerShell, and you MUST use 'python' instead of 'python3' to execute Python scripts.

Guidelines:
1. First, explore the directory structure or read relevant files to understand the project.
2. When modifying files, prefer `patch_file` over `write_file` for partial changes. Make sure your target blocks match exactly.
3. After making code modifications, ALWAYS run appropriate tests or validation commands (e.g., pytest, compiler check) using `run_command` to ensure your changes work and don't break existing functionality.
4. Work step-by-step. Do not rush to complete the task. Check and verify each step.
5. All your explanations and final summaries to the user MUST be written in Japanese.

TOOL CALLING FORMAT:
If your environment does not support native function calling, you MUST write your tool call as a JSON object in a Markdown code block like this:
```json
{
  "name": "write_file",
  "arguments": {
    "path": "hello.py",
    "content": "print('Hello')"
  }
}
```
Only call ONE tool per message. Do not include multiple tool calls or any additional text when you output the JSON.
"""

def extract_tool_calls_from_text(text: str) -> List[Dict[str, Any]]:
    """
    OllamaがFunction Callingを処理できず、テキストにJSONを出力した場合に、
    テキストからツール呼び出し情報を抽出する。
    """
    tool_calls = []
    
    # 1. ```json ... ``` ブロックから抽出
    json_blocks = re.findall(r'```json\s*(.*?)\s*```', text, re.DOTALL)
    for block in json_blocks:
        try:
            data = json.loads(block.strip())
            if isinstance(data, dict) and "name" in data:
                tool_calls.append({
                    "function": {
                        "name": data["name"],
                        "arguments": data.get("arguments") or data.get("parameters") or {}
                    }
                })
        except Exception:
            pass

    if tool_calls:
        return tool_calls

    # 2. テキスト中の { から } までの最初の単一オブジェクトをパース試行
    match = re.search(r'(\{.*?\})', text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(1).strip())
            if isinstance(data, dict) and "name" in data:
                tool_calls.append({
                    "function": {
                        "name": data["name"],
                        "arguments": data.get("arguments") or data.get("parameters") or {}
                    }
                })
        except Exception:
            pass
            
    if tool_calls:
        return tool_calls

    # 3. 最も外側にある { と } を探して、パース試行
    start_idx = text.find('{')
    end_idx = text.rfind('}')
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        try:
            data = json.loads(text[start_idx:end_idx+1].strip())
            if isinstance(data, dict) and "name" in data:
                tool_calls.append({
                    "function": {
                        "name": data["name"],
                        "arguments": data.get("arguments") or data.get("parameters") or {}
                    }
                })
        except Exception:
            pass

    return tool_calls

def call_ollama(messages: List[Dict[str, Any]], use_tools: bool = True) -> Dict[str, Any]:
    """
    Ollamaの /api/chat を呼び出す。
    """
    payload = {
        "model": config.DOCA_MODEL,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": 0.1
        }
    }
    if use_tools:
        payload["tools"] = tools.TOOLS_DEFINITION

    url = f"{config.OLLAMA_HOST}/api/chat"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    
    logger.log_debug(f"Ollama API呼び出し開始: {url} | モデル: {config.DOCA_MODEL}")
    logger.log_debug(f"Ollama ペイロード: {json.dumps(payload, ensure_ascii=False)}")
    
    try:
        with urllib.request.urlopen(req, timeout=120) as res:
            resp_bytes = res.read()
            resp_str = resp_bytes.decode("utf-8")
            logger.log_debug(f"Ollama レスポンス取得: {resp_str}")
            return json.loads(resp_str)
    except urllib.error.URLError as e:
        logger.log_error(f"Ollama 接続失敗: {str(e)}")
        raise ConnectionError(f"Failed to connect to Ollama at '{config.OLLAMA_HOST}'. Ensure Ollama is running. Error: {str(e)}")

def run_agent_loop(
    task: str,
    on_progress: Optional[Callable[[str, int], None]] = None,
    history: Optional[List[Dict[str, Any]]] = None,
    is_cancelled: Optional[Callable[[], bool]] = None,
    allowed_paths: Optional[List[str]] = None
) -> str:
    """
    思考ループを実行する。

    allowed_paths: 親エージェントから渡された、WORKSPACE_DIR 以外で追加的に
    読み書きを許可するディレクトリのリスト。タスク（実行コンテキスト）単位で
    config.EXTRA_ALLOWED_PATHS に登録する。
    """
    # 親エージェントから渡された追加の許可パスを登録する。
    # 空でも必ず set することで、スレッド再利用時に前タスクの設定が残らないようにする。
    normalized_allowed = tuple(
        os.path.abspath(p)
        for p in (allowed_paths or [])
        if isinstance(p, str) and p.strip()
    )
    config.EXTRA_ALLOWED_PATHS.set(normalized_allowed)

    logger.log_info(f"エージェント思考ループ開始: タスク='{task}'")
    if normalized_allowed:
        logger.log_info(f"親エージェントから追加の書き込み許可パスを受領: {list(normalized_allowed)}")
    if history is None:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    else:
        messages = history
        if not any(m["role"] == "system" for m in messages):
            messages.insert(0, {"role": "system", "content": SYSTEM_PROMPT})
            
    messages.append({"role": "user", "content": task})
    
    max_iterations = 20
    current_iteration = 0
    
    if on_progress:
        on_progress("思考を開始しています...", 5)
        
    final_response = ""
    
    while current_iteration < max_iterations:
        if is_cancelled and is_cancelled():
            cancel_msg = "\n\n⚠️ タスクがユーザーまたは親エージェントによってキャンセルされました。"
            final_response += cancel_msg
            logger.log_warning("タスクキャンセル要求を検知しました。ループを抜けます。")
            if on_progress:
                on_progress("タスクはキャンセルされました。", 100)
            break

        current_iteration += 1
        progress_percent = int(5 + (current_iteration / max_iterations) * 90)
        logger.log_info(f"思考ループ イテレーション {current_iteration}/{max_iterations}")
        
        if on_progress:
            on_progress(f"Ollama ({config.DOCA_MODEL}) に問い合わせ中...", progress_percent)
            
        try:
            response = call_ollama(messages, use_tools=True)
        except Exception as e:
            err_msg = f"Ollamaの呼び出し中にエラーが発生しました: {str(e)}"
            logger.log_error(err_msg, exc_info=True)
            if on_progress:
                on_progress(err_msg, 100)
            return err_msg
            
        message = response.get("message", {})
        messages.append(message)
        
        content = message.get("content", "")
        if content:
            final_response = content
            logger.log_debug(f"LLMテキスト応答: {content}")
            
        tool_calls = message.get("tool_calls")
        if not tool_calls:
            if content:
                tool_calls = extract_tool_calls_from_text(content)

        if not tool_calls:
            logger.log_info("ツール呼び出し指示がありません。ループを正常終了します。")
            break
            
        for tool_call in tool_calls:
            func_info = tool_call.get("function", {})
            func_name = func_info.get("name")
            func_args = func_info.get("arguments", {})
            
            if isinstance(func_args, str):
                try:
                    func_args = json.loads(func_args)
                except Exception:
                    pass
                    
            logger.log_info(f"ツール実行要求: {func_name}({func_args})")
            if on_progress:
                on_progress(f"ツール実行中: {func_name}({func_args})", progress_percent)
                
            tool_func = tools.TOOLS_MAP.get(func_name)
            if tool_func:
                try:
                    tool_result = tool_func(**func_args)
                except Exception as e:
                    tool_result = f"Error during execution: {str(e)}\n{traceback.format_exc()}"
                    logger.log_error(f"ツール実行中にエラーが発生しました: {str(e)}", exc_info=True)
            else:
                tool_result = f"Error: Tool '{func_name}' is not defined."
                logger.log_error(tool_result)
                
            logger.log_info(f"ツール実行結果 ({func_name}): {str(tool_result)[:300]}...")
            
            messages.append({
                "role": "tool",
                "content": str(tool_result),
                "name": func_name
            })
            
    if current_iteration >= max_iterations:
        warn_msg = "\n\n⚠️ 警告: 最大ループ回数（20回）に達したため、処理を中断しました。"
        final_response += warn_msg
        logger.log_warning("最大ループ回数（20回）に達しました。")
        if on_progress:
            on_progress("処理中断（最大ループ到達）", 100)
    else:
        logger.log_info("エージェント思考ループ正常終了。")
        if on_progress:
            on_progress("タスク完了", 100)
            
    return final_response
