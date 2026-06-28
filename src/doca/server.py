import os
import sys
import json
import socket
import asyncio
import uuid
import urllib.request
from typing import Dict, Any, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, BackgroundTasks, Request, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from doca import config
from doca import agent
from doca import logger

# ポート検出用
actual_port = config.DEFAULT_PORT

# タスク管理ストア
# task_id -> { "status": "TASK_STATE_...", "result": {...}, "cancelled": False, "history": [] }
tasks_db: Dict[str, Any] = {}

# SSE配信用の進捗キュー
# task_id -> asyncio.Queue
progress_queues: Dict[str, asyncio.Queue] = {}

def find_free_port(start_port: int) -> int:
    """利用可能な空きポートを検索する"""
    port = start_port
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except socket.error:
                port += 1

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 起動直後に待受URLを含んだ ready シグナルを stdout に1行だけ出力する (Part B §S3準拠)
    ready_data = {
        "a2a": "ready",
        "url": f"http://127.0.0.1:{actual_port}",
        "agent": "doca",
        "version": "0.1.0"
    }
    sys.stdout.write(json.dumps(ready_data) + "\n")
    sys.stdout.flush()
    yield

app = FastAPI(lifespan=lifespan)

# CORSを許可
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def send_webhook(url: str, payload: dict):
    """標準ライブラリのurllibを使ってWebhookをPOST送信する"""
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as res:
            res.read()
        logger.log_info(f"Webhook通知送信成功: {url}")
    except Exception as e:
        logger.log_error(f"Webhook送信失敗 ({url}): {str(e)}", exc_info=True)
        sys.stderr.write(f"Webhook送信失敗 ({url}): {str(e)}\n")
        sys.stderr.flush()

async def execute_task_async(task_id: str, task_prompt: str, callback_url: str = None, workspace_paths: List[str] = None):
    """エージェント思考ループをバックグラウンドで実行する"""
    tasks_db[task_id]["status"] = "TASK_STATE_WORKING"
    queue = progress_queues[task_id]
    loop = asyncio.get_running_loop()
    
    # SSE進捗通知用ヘルパー
    def on_progress(msg: str, percent: int):
        # メモリDBの更新
        tasks_db[task_id]["last_progress"] = {"message": msg, "percentage": percent}
        # SSEキューへの格納（ノンブロッキング）
        loop.call_soon_threadsafe(
            queue.put_nowait,
            {"taskId": task_id, "message": msg, "percentage": percent}
        )

    # キャンセル判定用ヘルパー
    def is_cancelled() -> bool:
        return tasks_db[task_id].get("cancelled", False)

    try:
        # LLMを実行（同期処理のため、別スレッドで安全に実行）
        final_answer = await loop.run_in_executor(
            None,
            agent.run_agent_loop,
            task_prompt,
            on_progress,
            tasks_db[task_id]["history"],
            is_cancelled,
            workspace_paths
        )
        
        if is_cancelled():
            tasks_db[task_id]["status"] = "TASK_STATE_CANCELED"
            success = False
            subject = "タスクはキャンセルされました。"
        else:
            tasks_db[task_id]["status"] = "TASK_STATE_COMPLETED"
            success = True
            subject = "タスクが正常に完了しました。"

        tasks_db[task_id]["result"] = {
            "subject": subject,
            "success": success,
            "content": final_answer
        }
    except Exception as e:
        tasks_db[task_id]["status"] = "TASK_STATE_FAILED"
        tasks_db[task_id]["result"] = {
            "subject": "タスクの実行中に致命的なエラーが発生しました。",
            "success": False,
            "content": str(e)
        }
        
    # SSE終了を伝えるシグナルをキューに投入
    loop.call_soon_threadsafe(
        queue.put_nowait,
        {"taskId": task_id, "status": tasks_db[task_id]["status"]}
    )

    # Webhook通知 (Part A §I3準拠)
    if callback_url:
        payload = {
            "taskId": task_id,
            "status": tasks_db[task_id]["status"],
            "result": tasks_db[task_id]["result"]
        }
        # 非同期スレッドでWebhookを送信
        await loop.run_in_executor(None, send_webhook, callback_url, payload)

# --- エンドポイント定義 ---

@app.get("/.well-known/agent-card.json")
def get_agent_card():
    """Agent Cardの公開 (Part A §I6準拠)"""
    return {
        "name": "doca",
        "version": "0.1.0",
        "description": "Ollamaバックエンドのミニマルコーディングエージェント",
        "capabilities": {
            "tools": True,
            # 親エージェント（クライアント）が使い方を理解できるよう、機能の入力契約を自己記述する。
            "workspacePaths": {
                "supported": True,
                "location": "params.configuration.workspacePaths",
                "type": "string[]",
                "description": (
                    "親エージェントがタスク単位で指定する作業フォルダのリスト。"
                    "先頭エントリがそのタスクの『作業ベースディレクトリ』となり、"
                    "ツールの相対パス解決基準および run_command の作業ディレクトリ(cwd)になる。"
                    "各エントリ配下は読み書きが許可される(エージェント起動時の WORKSPACE_DIR に追加して)。"
                    "未指定時は WORKSPACE_DIR(エージェント起動ディレクトリ)が基準。"
                    "成果物を特定フォルダに格納させたい場合は、そのフォルダを先頭に指定すること。"
                ),
                "example": {
                    "method": "SendMessage",
                    "params": {
                        "message": {"parts": [{"text": "fibonacci.py を作成してください"}]},
                        "configuration": {"workspacePaths": ["S:/work/develop/temp"]}
                    }
                }
            }
        },
        "skills": [
            {
                "name": "coding",
                "description": "Windows 11 (PowerShell) 上での自律的なファイル操作とコマンド実行によるコーディング支援"
            }
        ]
    }

@app.post("/rpc")
async def json_rpc_handler(request: Request, background_tasks: BackgroundTasks):
    """A2A v1.0 JSON-RPCハンドラ (Part A §I8準拠)"""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
        
    # バージョンヘッダーチェック
    a2a_version = request.headers.get("A2A-Version")
    # Mnemo共通規約 v0.2では 1.0 必須
    if a2a_version != "1.0":
        sys.stderr.write(f"Warning: Unexpected A2A-Version header: {a2a_version}\n")
        sys.stderr.flush()

    rpc_id = body.get("id")
    method = body.get("method")
    params = body.get("params", {})

    logger.log_info(f"JSON-RPC要求受信: id={rpc_id}, method={method}")

    if not method:
        return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32600, "message": "Invalid Request: 'method' is required"}}

    # --- SendMessage (タスク投入) ---
    if method == "SendMessage":
        message_data = params.get("message", {})
        parts = message_data.get("parts", [])
        
        # タスク内容の抽出
        task_text = ""
        for part in parts:
            if "text" in part:
                task_text += part["text"]

        if not task_text:
            return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32602, "message": "Invalid Params: task text is empty"}}

        # タスクIDの生成
        task_id = str(uuid.uuid4())
        
        # Webhook URL の抽出 (A2A 規約: params["configuration"]["pushNotificationConfig"]["url"] もしくは直下)
        callback_url = None
        if "configuration" in params and isinstance(params["configuration"], dict):
            cfg = params["configuration"]
            if "pushNotificationConfig" in cfg and isinstance(cfg["pushNotificationConfig"], dict):
                callback_url = cfg["pushNotificationConfig"].get("url")
        if not callback_url:
            callback_url = params.get("callbackUrl") or params.get("webhookUrl") or params.get("callback_url") or params.get("webhook_url")

        # 親エージェントから渡される書き込み許可パスの抽出
        # (A2A 規約: params["configuration"]["workspacePaths"] もしくは params 直下)
        workspace_paths: List[str] = []
        if "configuration" in params and isinstance(params["configuration"], dict):
            wp = params["configuration"].get("workspacePaths")
            if isinstance(wp, list):
                workspace_paths = [p for p in wp if isinstance(p, str)]
        if not workspace_paths:
            wp = params.get("workspacePaths")
            if isinstance(wp, list):
                workspace_paths = [p for p in wp if isinstance(p, str)]

        # DB登録
        tasks_db[task_id] = {
            "status": "TASK_STATE_SUBMITTED",
            "result": None,
            "cancelled": False,
            "history": [],
            "last_progress": {"message": "タスクが投入されました", "percentage": 0}
        }
        progress_queues[task_id] = asyncio.Queue()

        # バックグラウンド実行
        background_tasks.add_task(execute_task_async, task_id, task_text, callback_url, workspace_paths)

        return {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {
                "task": {
                    "id": task_id,
                    "status": {"state": "TASK_STATE_SUBMITTED"}
                }
            }
        }

    # --- GetTask (タスク状態取得) ---
    elif method == "GetTask":
        task_id = params.get("id")
        if not task_id or task_id not in tasks_db:
            return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32602, "message": f"Task '{task_id}' not found"}}

        task_data = tasks_db[task_id]
        response_data = {
            "task": {
                "id": task_id,
                "status": {"state": task_data["status"]}
            }
        }
        if task_data["result"]:
            response_data["task"]["result"] = task_data["result"]

        return {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": response_data
        }

    # --- CancelTask (タスクキャンセル) ---
    elif method == "CancelTask":
        task_id = params.get("id")
        if not task_id or task_id not in tasks_db:
            return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32602, "message": f"Task '{task_id}' not found"}}

        tasks_db[task_id]["cancelled"] = True
        # 進行中（WORKING）ならステータスをキャンセル中に仮更新
        if tasks_db[task_id]["status"] == "TASK_STATE_WORKING":
            tasks_db[task_id]["status"] = "TASK_STATE_CANCELED"

        return {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {
                "task": {
                    "id": task_id,
                    "status": {"state": tasks_db[task_id]["status"]}
                }
            }
        }

    else:
        return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32601, "message": f"Method not found: '{method}'"}}


@app.get("/tasks/{task_id}/events")
async def get_task_events(task_id: str):
    """SSEによる特定タスクの進捗配信 (Part A §I3準拠)"""
    if task_id not in progress_queues:
        raise HTTPException(status_code=404, detail="Task not found")

    async def sse_generator():
        queue = progress_queues[task_id]
        
        # クライアント接続時の初期進捗を流す
        initial_progress = tasks_db[task_id].get("last_progress")
        if initial_progress:
            yield f"data: {json.dumps(initial_progress)}\n\n"

        while True:
            try:
                # キューにデータが入るのを待機
                event = await asyncio.wait_for(queue.get(), timeout=2.0)
                yield f"data: {json.dumps(event)}\n\n"
                
                # タスクが終了状態になったら配信を終える
                if "status" in event and event["status"] in ["TASK_STATE_COMPLETED", "TASK_STATE_FAILED", "TASK_STATE_CANCELED"]:
                    break
            except asyncio.TimeoutError:
                # 接続維持のためのキープアライブ
                yield ": keep-alive\n\n"
            except ConnectionError:
                break

    return StreamingResponse(sse_generator(), media_type="text/event-stream")

def run_server():
    """
    FastAPI + Uvicorn サーバーを起動する。
    ポートは空いているものを動的に探索する。
    """
    global actual_port
    actual_port = find_free_port(config.DEFAULT_PORT)
    
    # Uvicornのアクセスログ等が stdout に混ざらないように、全ての出力を stderr に向ける
    log_config = uvicorn.config.LOGGING_CONFIG
    for logger_name in ["uvicorn", "uvicorn.error", "uvicorn.access"]:
        if logger_name in log_config["loggers"]:
            log_config["loggers"][logger_name]["propagate"] = False
    for handler_name, handler in log_config["handlers"].items():
        if handler.get("stream") == "ext://sys.stdout":
            handler["stream"] = "ext://sys.stderr"
            
    logger.log_info(f"Doca A2A サーバー起動開始 (ポート: {actual_port})")
    
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=actual_port,
        log_level="info",
        log_config=log_config
    )
