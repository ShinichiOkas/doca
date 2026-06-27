import unittest
from unittest.mock import patch, MagicMock
import json
import asyncio
from fastapi.testclient import TestClient
from doca.server import app, tasks_db, progress_queues

class TestServer(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        tasks_db.clear()
        progress_queues.clear()

    def test_agent_card(self):
        response = self.client.get("/.well-known/agent-card.json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "doca")
        self.assertIn("coding", [s["name"] for s in data["skills"]])

    @patch("doca.server.execute_task_async")
    def test_json_rpc_send_message(self, mock_execute_task):
        # SendMessageの呼び出し
        payload = {
            "jsonrpc": "2.0",
            "id": "req-1",
            "method": "SendMessage",
            "params": {
                "message": {
                    "messageId": "msg-1",
                    "role": "ROLE_USER",
                    "parts": [{"text": "テストタスクです"}]
                },
                "callbackUrl": "http://example.com/webhook"
            }
        }
        
        headers = {"A2A-Version": "1.0"}
        response = self.client.post("/rpc", json=payload, headers=headers)
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertIn("result", data)
        task_id = data["result"]["task"]["id"]
        self.assertEqual(data["result"]["task"]["status"]["state"], "TASK_STATE_SUBMITTED")
        
        # バックグラウンドタスクがスケジューリングされたか
        mock_execute_task.assert_called_once()
        args = mock_execute_task.call_args[0]
        self.assertEqual(args[0], task_id)
        self.assertEqual(args[1], "テストタスクです")
        self.assertEqual(args[2], "http://example.com/webhook")

    @patch("doca.server.execute_task_async")
    def test_json_rpc_send_message_a2a_spec_webhook(self, mock_execute_task):
        # A2A v1.0規格のネストされたWebhook URL指定のテスト
        payload = {
            "jsonrpc": "2.0",
            "id": "req-1b",
            "method": "SendMessage",
            "params": {
                "message": {
                    "messageId": "msg-1b",
                    "role": "ROLE_USER",
                    "parts": [{"text": "テストタスクです"}]
                },
                "configuration": {
                    "pushNotificationConfig": {
                        "url": "http://example.com/webhook-a2a"
                    }
                }
            }
        }
        
        headers = {"A2A-Version": "1.0"}
        response = self.client.post("/rpc", json=payload, headers=headers)
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertIn("result", data)
        task_id = data["result"]["task"]["id"]
        
        # バックグラウンドタスクが正しい引数で呼び出されたか
        mock_execute_task.assert_called_once()
        args = mock_execute_task.call_args[0]
        self.assertEqual(args[0], task_id)
        self.assertEqual(args[1], "テストタスクです")
        self.assertEqual(args[2], "http://example.com/webhook-a2a")

    @patch("doca.server.execute_task_async")
    def test_json_rpc_send_message_workspace_paths(self, mock_execute_task):
        # 親エージェントが configuration.workspacePaths で許可パスを渡すケース
        payload = {
            "jsonrpc": "2.0",
            "id": "req-1c",
            "method": "SendMessage",
            "params": {
                "message": {
                    "messageId": "msg-1c",
                    "role": "ROLE_USER",
                    "parts": [{"text": "成果物を temp に格納してください"}]
                },
                "configuration": {
                    "workspacePaths": ["S:/work/develop/temp"]
                }
            }
        }

        headers = {"A2A-Version": "1.0"}
        response = self.client.post("/rpc", json=payload, headers=headers)
        self.assertEqual(response.status_code, 200)

        mock_execute_task.assert_called_once()
        args = mock_execute_task.call_args[0]
        # args: (task_id, task_text, callback_url, workspace_paths)
        self.assertEqual(args[1], "成果物を temp に格納してください")
        self.assertEqual(args[3], ["S:/work/develop/temp"])

    def test_json_rpc_get_task_not_found(self):
        payload = {
            "jsonrpc": "2.0",
            "id": "req-2",
            "method": "GetTask",
            "params": {"id": "nonexistent-id"}
        }
        response = self.client.post("/rpc", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("error", data)

    def test_json_rpc_cancel_task(self):
        # 進行中のタスクを偽装登録
        task_id = "test-task-123"
        tasks_db[task_id] = {
            "status": "TASK_STATE_WORKING",
            "result": None,
            "cancelled": False
        }
        
        payload = {
            "jsonrpc": "2.0",
            "id": "req-3",
            "method": "CancelTask",
            "params": {"id": task_id}
        }
        response = self.client.post("/rpc", json=payload)
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertEqual(data["result"]["task"]["status"]["state"], "TASK_STATE_CANCELED")
        self.assertTrue(tasks_db[task_id]["cancelled"])

    def test_sse_endpoint_not_found(self):
        response = self.client.get("/tasks/nonexistent/events")
        self.assertEqual(response.status_code, 404)

    def test_sse_endpoint_stream(self):
        # タスクとキューの登録
        task_id = "task-sse"
        tasks_db[task_id] = {
            "status": "TASK_STATE_WORKING",
            "last_progress": {"message": "開始", "percentage": 10}
        }
        queue = asyncio.Queue()
        progress_queues[task_id] = queue
        
        # キューに擬似進捗と完了シグナルを入れる
        queue.put_nowait({"message": "実行中", "percentage": 50})
        queue.put_nowait({"status": "TASK_STATE_COMPLETED"})
        
        # SSEエンドポイントへアクセスし、データを読み出す
        response = self.client.get(f"/tasks/{task_id}/events")
        self.assertEqual(response.status_code, 200)
        
        # ストリームの出力をパース
        events = []
        for line in response.iter_lines():
            if line.startswith("data: "):
                event_data = json.loads(line[len("data: "):])
                events.append(event_data)
                
        # イベントの流れを検証
        self.assertEqual(len(events), 3)
        self.assertEqual(events[0]["message"], "開始") # 初期進捗
        self.assertEqual(events[1]["message"], "実行中") # キュー進捗
        self.assertEqual(events[2]["status"], "TASK_STATE_COMPLETED") # 完了シグナル

if __name__ == "__main__":
    unittest.main()
