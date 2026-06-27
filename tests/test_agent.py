import unittest
from unittest.mock import patch, MagicMock
import json
import io
from doca import agent
from doca import tools

class TestAgent(unittest.TestCase):
    
    @patch("urllib.request.urlopen")
    def test_run_agent_loop_with_tool_call(self, mock_urlopen):
        # Ollama APIのモックレスポンスを定義
        # 1回目のレスポンス: ツール呼び出し指示
        res_tool_call = {
            "message": {
                "role": "assistant",
                "tool_calls": [
                    {
                        "function": {
                            "name": "read_file",
                            "arguments": {"path": "dummy.txt"}
                        }
                    }
                ]
            }
        }
        # 2回目のレスポンス: 最終解答
        res_final = {
            "message": {
                "role": "assistant",
                "content": "ダミーファイルの内容を確認しました。"
            }
        }
        
        # urlopenの戻り値をモック
        mock_res1 = MagicMock()
        mock_res1.__enter__.return_value = mock_res1
        mock_res1.read.return_value = json.dumps(res_tool_call).encode("utf-8")
        
        mock_res2 = MagicMock()
        mock_res2.__enter__.return_value = mock_res2
        mock_res2.read.return_value = json.dumps(res_final).encode("utf-8")
        
        # 連続した呼び出しに対する戻り値を設定
        mock_urlopen.side_effect = [
            mock_res1,
            mock_res2
        ]
        
        # read_file ツールのモック
        original_read_file = tools.TOOLS_MAP["read_file"]
        tools.TOOLS_MAP["read_file"] = MagicMock(return_value="dummy file content")
        
        # 進捗コールバックの記録用
        progress_log = []
        def on_progress(msg, percent):
            progress_log.append((msg, percent))
            
        try:
            # 思考ループ実行
            result = agent.run_agent_loop("dummy.txtを読んでください", on_progress=on_progress)
            
            # 検証
            self.assertEqual(result, "ダミーファイルの内容を確認しました。")
            # ツールが呼ばれたか確認
            tools.TOOLS_MAP["read_file"].assert_called_once_with(path="dummy.txt")
            # urlopenが2回呼ばれたか確認
            self.assertEqual(mock_urlopen.call_count, 2)
            # 進捗ログに進捗率100%が含まれているか確認
            self.assertEqual(progress_log[-1][1], 100)
            
        finally:
            # ツールを元に戻す
            tools.TOOLS_MAP["read_file"] = original_read_file

    @patch("urllib.request.urlopen")
    def test_run_agent_loop_cancel(self, mock_urlopen):
        # 思考ループ中にキャンセルされるケースをテスト
        # 常にツール呼び出しを返すようなレスポンスをモック
        res_tool_call = {
            "message": {
                "role": "assistant",
                "tool_calls": [
                    {
                        "function": {
                            "name": "read_file",
                            "arguments": {"path": "dummy.txt"}
                        }
                    }
                ]
            }
        }
        mock_res = MagicMock()
        mock_res.__enter__.return_value = mock_res
        mock_res.read.return_value = json.dumps(res_tool_call).encode("utf-8")
        mock_urlopen.return_value = mock_res
        
        # 2回目のイテレーションでキャンセルされるように設定
        call_count = 0
        def is_cancelled():
            nonlocal call_count
            call_count += 1
            return call_count > 1  # 2回目以降にTrueを返す

        # 思考ループ実行
        result = agent.run_agent_loop("無限ループテスト", is_cancelled=is_cancelled)
        
        # キャンセルで終了したことを確認
        self.assertIn("キャンセルされました", result)
        # urlopenが1回しか呼ばれていない（2回目に入る前にキャンセル検知でブレイクしたため）
        self.assertEqual(mock_urlopen.call_count, 1)

if __name__ == "__main__":
    unittest.main()
