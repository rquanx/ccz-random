"""Execute one game case with timeout and exact descendant ownership."""
import subprocess
import sys
import time

from tests.helpers.windows_job import TestProcessJob


def run_case_process(script, repo_root, environment, timeout_seconds):
    with TestProcessJob() as job:
        environment = dict(environment, CCZ_TEST_JOB_NAME=job.name, PYTHONFAULTHANDLER="1")
        with subprocess.Popen(
            [sys.executable, "-m", "tests.helpers.windows_job", str(script)],
            cwd=repo_root, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ) as process:
            timed_out = False
            try:
                stdout, stderr = process.communicate(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                timed_out = True
                job.terminate()
                stdout, stderr = process.communicate(timeout=10)
            except BaseException:
                job.terminate()
                if process.poll() is None:
                    process.kill()
                process.communicate(timeout=10)
                raise
            lingering = job.process_ids()
            if lingering:
                job.terminate()
            # TerminateJobObject is asynchronous; finish before deleting the copy.
            deadline = time.monotonic() + 10
            while job.process_ids():
                if time.monotonic() >= deadline:
                    raise TimeoutError("测试所属进程树未能退出")
                time.sleep(.01)
            return_code = 124 if timed_out else (125 if lingering and process.returncode == 0 else process.returncode)
            if timed_out:
                stderr += f"\n测试超过 {timeout_seconds} 秒，已终止所属进程树。"
            elif lingering:
                stderr += "\n已清理测试自身的残留进程：" + ",".join(map(str, lingering))
            return subprocess.CompletedProcess(process.args, return_code, stdout, stderr), timed_out, lingering
