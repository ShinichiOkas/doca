import os
import tempfile
import unittest
import shutil
import platform
from doca import tools
from doca import config

class TestTools(unittest.TestCase):
    def setUp(self):
        # テスト用の一時的なワークスペースディレクトリを作成
        self.test_dir = tempfile.mkdtemp()
        self.original_workspace = config.WORKSPACE_DIR
        config.WORKSPACE_DIR = os.path.abspath(self.test_dir)
        # 追加許可パスは毎テスト空に戻す
        self._allowed_token = config.EXTRA_ALLOWED_PATHS.set(())

    def tearDown(self):
        # テスト後のお掃除
        config.WORKSPACE_DIR = self.original_workspace
        config.EXTRA_ALLOWED_PATHS.reset(self._allowed_token)
        shutil.rmtree(self.test_dir)

    def test_write_and_read_file(self):
        # ファイルの書き込みテスト
        res = tools.write_file("test.txt", "hello world")
        self.assertIn("Success", res)
        
        # ファイルの読み込みテスト
        content = tools.read_file("test.txt")
        self.assertEqual(content, "hello world")

    def test_patch_file_success(self):
        # 初期ファイル書き込み
        tools.write_file("patch_test.txt", "line1\nline2\nline3")
        
        # パッチ適用
        res = tools.patch_file("patch_test.txt", "line2", "replaced_line2")
        self.assertIn("Success", res)
        
        # 結果の確認
        content = tools.read_file("patch_test.txt")
        self.assertEqual(content, "line1\nreplaced_line2\nline3")

    def test_patch_file_not_found(self):
        tools.write_file("patch_test.txt", "line1\nline2\nline3")
        res = tools.patch_file("patch_test.txt", "nonexistent", "new")
        self.assertIn("Error", res)

    def test_patch_file_not_unique(self):
        tools.write_file("patch_test.txt", "dup\ndup\nline3")
        res = tools.patch_file("patch_test.txt", "dup", "new")
        self.assertIn("Error", res)

    def test_delete_file(self):
        tools.write_file("del_test.txt", "temp")
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "del_test.txt")))
        
        # 削除
        res = tools.delete_file("del_test.txt")
        self.assertIn("Success", res)
        self.assertFalse(os.path.exists(os.path.join(self.test_dir, "del_test.txt")))

    def test_secure_path_prevention(self):
        # ワークスペース外へのアクセス制限をテスト
        with self.assertRaises(ValueError):
            tools._secure_path("../outside.txt")
            
        with self.assertRaises(ValueError):
            # 絶対パスでのワークスペース外指定
            tools._secure_path("C:/windows/system32/cmd.exe" if platform.system() == "Windows" else "/etc/passwd")

    def test_extra_allowed_path_grants_write(self):
        # WORKSPACE_DIR の外（兄弟ディレクトリ）を追加許可パスとして登録すると書き込めること
        coworking = tempfile.mkdtemp()
        try:
            target = os.path.join(coworking, "out.txt")
            # 許可前は拒否される
            with self.assertRaises(ValueError):
                tools._secure_path(target)
            # 親エージェントから渡された想定で許可パスを登録
            config.EXTRA_ALLOWED_PATHS.set((os.path.abspath(coworking),))
            res = tools.write_file(target, "from parent")
            self.assertIn("Success", res)
            with open(target, "r", encoding="utf-8") as f:
                self.assertEqual(f.read(), "from parent")
        finally:
            shutil.rmtree(coworking)

    def test_extra_allowed_path_no_prefix_leak(self):
        # 前方一致による誤許可が起きないこと（許可: '...foo' / 拒否対象: '...foo-secret'）
        base = tempfile.mkdtemp()
        try:
            allowed = os.path.join(base, "foo")
            sibling = os.path.join(base, "foo-secret")
            os.makedirs(allowed)
            os.makedirs(sibling)
            config.EXTRA_ALLOWED_PATHS.set((os.path.abspath(allowed),))
            # 許可ディレクトリ配下はOK
            tools._secure_path(os.path.join(allowed, "ok.txt"))
            # 名前が前方一致する兄弟ディレクトリは拒否される
            with self.assertRaises(ValueError):
                tools._secure_path(os.path.join(sibling, "leak.txt"))
        finally:
            shutil.rmtree(base)

    def test_run_command(self):
        # コマンド実行テスト
        # Windows 11 / Windows では PowerShell 経由、UNIX系では通常のシェル経由で動作
        if platform.system() == "Windows":
            res = tools.run_command("Write-Output 'hello from powershell'")
            self.assertIn("hello from powershell", res)
            self.assertIn("Exit Code: 0", res)
        else:
            res = tools.run_command("echo 'hello from shell'")
            self.assertIn("hello from shell", res)
            self.assertIn("Exit Code: 0", res)

if __name__ == "__main__":
    unittest.main()
