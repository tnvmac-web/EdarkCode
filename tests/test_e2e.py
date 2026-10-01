"""End-to-end tests: the real CLI binary and a real HTTP server, no API key needed."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable


def run_cli(*args: str, cwd: Path | None = None, timeout: int = 120) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.pop("EDARKCODE_LLM__API_KEY", None)
    env["EDARKCODE_DATA_DIR"] = str(Path(cwd or REPO_ROOT) / ".edarkcode-e2e")
    return subprocess.run(
        [PYTHON, "-m", "edarkcode.cli", *args],
        cwd=str(cwd or REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for_health(url: str, timeout: float = 40.0) -> dict:
    deadline = time.time() + timeout
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:  # noqa: S310
                return json.loads(resp.read())
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
            last_err = e
            time.sleep(0.4)
    raise AssertionError(f"server did not become healthy: {last_err}")


def test_cli_version():
    result = run_cli("version")
    assert result.returncode == 0, result.stderr
    assert "edarkcode" in result.stdout


def test_cli_help_lists_commands():
    result = run_cli("--help")
    assert result.returncode == 0, result.stderr
    for cmd in ("run", "chat", "serve", "config", "memory", "doctor"):
        assert cmd in result.stdout


def test_cli_doctor_without_key_exits_nonzero():
    result = run_cli("doctor")
    assert result.returncode == 1
    assert "No API key" in result.stdout


def test_cli_run_without_key_fails_cleanly(tmp_path):
    """No key -> the agent must report an error, not crash with a traceback."""
    (tmp_path / "x.txt").write_text("hi", encoding="utf-8")
    result = run_cli("run", "say hello", "--workspace", str(tmp_path), "--yes")
    assert "Traceback" not in result.stderr, result.stderr
    assert result.returncode == 1


def test_cli_memory_and_config_roundtrip(tmp_path):
    result = run_cli("config", "init", cwd=tmp_path)
    assert result.returncode == 0, result.stderr

    result = run_cli("config", "show", cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert "provider" in result.stdout

    result = run_cli("memory", "list", cwd=tmp_path)
    assert result.returncode == 0, result.stderr


def test_server_serves_health_and_index(tmp_path):
    port = free_port()
    env = dict(os.environ)
    env["EDARKCODE_DATA_DIR"] = str(tmp_path / ".edarkcode-e2e")
    env.pop("EDARKCODE_LLM__API_KEY", None)
    proc = subprocess.Popen(
        [PYTHON, "-m", "edarkcode.cli", "serve", "--host", "127.0.0.1", "--port", str(port),
         "--workspace", str(tmp_path)],
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )
    try:
        health = wait_for_health(f"http://127.0.0.1:{port}/api/health")
        assert health["status"] == "ok"
        assert health["api_key_configured"] is False

        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as resp:  # noqa: S310
            html = resp.read().decode()
        assert "edarkcode" in html

        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/tools", timeout=5) as resp:  # noqa: S310
            tools = json.loads(resp.read())
        names = {t["name"] for t in tools["tools"]}
        assert "run_shell" in names
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.mark.skipif(
    not os.environ.get("EDARKCODE_E2E_LLM"),
    reason="set EDARKCODE_E2E_LLM=1 and a real API key to run the live agent e2e",
)
def test_live_agent_creates_a_file(tmp_path):
    """Real end-to-end: a live model must actually create a file on disk."""
    result = run_cli(
        "run",
        "Create a file called e2e_proof.txt containing exactly the word verified",
        "--workspace",
        str(tmp_path),
        "--yes",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    proof = tmp_path / "e2e_proof.txt"
    assert proof.exists(), f"agent did not create the file.\n{result.stdout}"
    assert "verified" in proof.read_text(encoding="utf-8")
