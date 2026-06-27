import os
import sys
import tempfile
import shutil
import subprocess
import unittest
import urllib.request
import json

# Ollama の接続確認
def is_ollama_available() -> bool:
    try:
        req = urllib.request.Request("http://localhost:11434")
        with urllib.request.urlopen(req, timeout=2) as res:
            return res.status == 200
    except Exception:
        return False

# テスト対象の実行ファイルパス
EXE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "dist", "doca.exe"))
OLLAMA_MODEL = os.environ.get("DOCA_MODEL") or "qwen2.5-coder:7b"

@unittest.skipIf(not is_ollama_available(), "Ollama is not running on http://localhost:11434")
class TestIntegration(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        # 使用するモデルがOllamaにプルされているか確認し、無ければプルを試みる
        print(f"\n[TestSetup] Checking if model '{OLLAMA_MODEL}' is pulled in Ollama...")
        try:
            req = urllib.request.Request("http://localhost:11434/api/tags")
            with urllib.request.urlopen(req, timeout=5) as res:
                tags_data = json.loads(res.read().decode("utf-8"))
                models = [m["name"] for m in tags_data.get("models", [])]
                
                # 'qwen2.5-coder:7b' または 'qwen2.5-coder:7b-instruct' などの部分一致を許容
                model_exists = any(OLLAMA_MODEL in m for m in models)
                
                if not model_exists:
                    print(f"[TestSetup] Model '{OLLAMA_MODEL}' not found. Attempting to pull...")
                    pull_payload = {"name": OLLAMA_MODEL, "stream": False}
                    pull_req = urllib.request.Request(
                        "http://localhost:11434/api/pull",
                        data=json.dumps(pull_payload).encode("utf-8"),
                        headers={"Content-Type": "application/json"}
                    )
                    with urllib.request.urlopen(pull_req, timeout=300) as pull_res:
                        pull_res.read()
                    print(f"[TestSetup] Successfully pulled '{OLLAMA_MODEL}'.")
                else:
                    print(f"[TestSetup] Model '{OLLAMA_MODEL}' is ready.")
        except Exception as e:
            print(f"[TestSetup] Warning while checking/pulling model: {str(e)}")

    def setUp(self):
        # テスト毎に隔離された一時ワークスペースを作成
        self.test_workspace = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_workspace)

    def tearDown(self):
        os.chdir(self.original_cwd)
        # 一時ワークスペースを削除
        shutil.rmtree(self.test_workspace)

    def run_doca_task(self, task_prompt: str) -> subprocess.CompletedProcess:
        """doca.exe を CLI モードで呼び出す"""
        # doca.exe が無い場合は python -m doca をフォールバックとして使用できるようにする
        if os.path.exists(EXE_PATH):
            cmd = [EXE_PATH, "--task", task_prompt]
        else:
            # PYTHONPATH を通して実行
            src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
            env = os.environ.copy()
            env["PYTHONPATH"] = src_path
            cmd = [sys.executable, "-m", "doca", "--task", task_prompt]
            return subprocess.run(cmd, capture_output=True, text=True, timeout=180, env=env)

        return subprocess.run(cmd, capture_output=True, text=True, timeout=180)

    def test_easy_hello_world(self):
        """簡単なお題: hello.py の作成と実行確認"""
        print("\n--- [Easy Test] Generating hello.py ---")
        task = "Create a python file named 'hello.py' that prints 'Hello, Doca!' when executed. Do not print anything else."
        
        result = self.run_doca_task(task)
        print(f"Doca CLI Stdout:\n{result.stdout}")
        print(f"Doca CLI Stderr:\n{result.stderr}")
        self.assertEqual(result.returncode, 0, "Doca task failed")

        # 生成されたファイルの確認
        hello_file = os.path.join(self.test_workspace, "hello.py")
        self.assertTrue(os.path.exists(hello_file), "hello.py was not created")

        # 実行テスト
        run_res = subprocess.run([sys.executable, hello_file], capture_output=True, text=True)
        self.assertEqual(run_res.returncode, 0)
        self.assertEqual(run_res.stdout.strip(), "Hello, Doca!")

    def test_medium_fibonacci(self):
        """中程度のお題: fib.py にフィボナッチ関数を実装し、アサート付きで自己検証させる"""
        print("\n--- [Medium Test] Fibonacci Implementation ---")
        task = "Write a python file named 'fib.py' containing a function 'fib(n)' that computes the n-th Fibonacci number. At the bottom of the file, add an assertion: 'assert fib(10) == 55'. Run the file using run_command to make sure the assertion passes."
        
        result = self.run_doca_task(task)
        print(f"Doca CLI Stdout:\n{result.stdout}")
        print(f"Doca CLI Stderr:\n{result.stderr}")
        self.assertEqual(result.returncode, 0, f"Doca task failed.\nStderr:\n{result.stderr}")

        fib_file = os.path.join(self.test_workspace, "fib.py")
        self.assertTrue(os.path.exists(fib_file), "fib.py was not created")

        # 正しくアサートが通るか実行検証
        run_res = subprocess.run([sys.executable, fib_file], capture_output=True, text=True)
        self.assertEqual(run_res.returncode, 0, "Generated fib.py failed assertion or had error")

    def test_hard_bug_fix(self):
        """難しいお題: バグがある calc.py とテストファイルを配置し、Docaにテストを流させ、バグを自己修正させてパスさせる"""
        print("\n--- [Hard Test] Debugging and Self-Correction ---")
        
        # バグのあるコードを先に配置
        calc_content = """def add(a, b):
    # Intentional bug: subtraction instead of addition
    return a - b

def divide(a, b):
    if b == 0:
        # Should raise ValueError as per test, but raises ZeroDivisionError
        return a / b
    return a / b
"""
        with open(os.path.join(self.test_workspace, "calc.py"), "w", encoding="utf-8") as f:
            f.write(calc_content)

        # テストスクリプトを配置
        test_content = """import pytest
import calc

def test_add():
    assert calc.add(2, 3) == 5

def test_divide_error():
    with pytest.raises(ValueError):
        calc.divide(10, 0)
"""
        with open(os.path.join(self.test_workspace, "test_calc.py"), "w", encoding="utf-8") as f:
            f.write(test_content)

        # 指示: pytestを実行し、エラーを検知させ、バグを直させて再テストでパスさせる
        task = "We have 'calc.py' and 'test_calc.py' in the workspace. First, execute pytest on 'test_calc.py' to see the failures. Then, patch 'calc.py' to fix the bugs: 1) add(a, b) should perform addition, and 2) divide(a, 0) should raise ValueError instead of division by zero. Finally, run pytest again to ensure all tests pass."

        result = self.run_doca_task(task)
        print(f"Doca CLI Stdout:\n{result.stdout}")
        print(f"Doca CLI Stderr:\n{result.stderr}")
        self.assertEqual(result.returncode, 0, f"Doca debugging task failed.\nStderr:\n{result.stderr}")

        # 最終的にテストがパスするか自身でも確認
        run_res = subprocess.run(["pytest", "test_calc.py"], capture_output=True, text=True)
        self.assertEqual(run_res.returncode, 0, f"Bugs were not completely fixed. pytest output:\n{run_res.stdout}\n{run_res.stderr}")

    def test_hard_gui_calculator(self):
        """最難関のお題: Tkinterを用いたGUI関数電卓アプリを自走作成し、自動終了テストモードで起動検証させる"""
        print("\n--- [Hard GUI Test] Creating GUI Scientific Calculator ---")
        
        task = (
            "Create a GUI-based scientific calculator application in a file named 'calculator.py' using Python's standard 'tkinter' library. "
            "It must support basic math operations (+, -, *, /) and scientific functions like square root (sqrt), power (^), and trigonometry (sin, cos). "
            "To allow automated testing, you MUST implement a test mode in calculator.py: if the environment variable 'TEST_MODE' is set to '1' "
            "OR if 'TEST_MODE=1' is passed as a command-line argument (in sys.argv), "
            "the application should automatically schedule the main window to destroy/close after 1000 milliseconds (using root.after(1000, root.destroy)). "
            "Finally, run the calculator using run_command to verify that it starts and closes successfully in test mode without any errors."
        )

        result = self.run_doca_task(task)
        print(f"Doca CLI Stdout:\n{result.stdout}")
        print(f"Doca CLI Stderr:\n{result.stderr}")
        self.assertEqual(result.returncode, 0, f"Doca GUI calculator task failed.\nStderr:\n{result.stderr}")

        calc_file = os.path.join(self.test_workspace, "calculator.py")
        self.assertTrue(os.path.exists(calc_file), "calculator.py was not created")

        # テストプロセス側でも実際に実行して自動終了するか検証する
        env = os.environ.copy()
        env["TEST_MODE"] = "1"
        
        try:
            run_res = subprocess.run(
                [sys.executable, calc_file, "TEST_MODE=1"],
                capture_output=True,
                text=True,
                env=env,
                timeout=5
            )
            self.assertEqual(run_res.returncode, 0, f"Calculator failed to run or exit properly: {run_res.stderr}")
            print("[TestSuccess] Calculator started and closed successfully in test mode.")
        except subprocess.TimeoutExpired:
            self.fail("Calculator did not close within 5 seconds under TEST_MODE=1. The auto-destroy logic might be missing.")

if __name__ == "__main__":
    unittest.main()
