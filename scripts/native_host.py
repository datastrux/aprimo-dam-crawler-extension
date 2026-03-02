from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import struct
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"

HOST_NAME = "com.datastrux.dam_audit_host"

PIPELINE_STAGES = [
    "01_crawl_citizens_images.py",
    "02_build_dam_fingerprints.py",
    "03_build_citizens_fingerprints.py",
    "04_match_assets.py",
    "05_build_reports.py",
]

PROGRESS_PREFIX = "AUDIT_PROGRESS "

# Load shared secret for HMAC verification
# Secret should be set during native host registration
SECRET_KEY_FILE = ROOT / ".audit_secret"
SECRET_KEY: bytes | None = None

if SECRET_KEY_FILE.exists():
    try:
        SECRET_KEY = SECRET_KEY_FILE.read_bytes().strip()
        sys.stderr.write(f"[NativeHost] Loaded HMAC secret ({len(SECRET_KEY)} bytes)\n")
    except Exception as e:
        sys.stderr.write(f"[NativeHost] Warning: Failed to load HMAC secret: {e}\n")
else:
    sys.stderr.write("[NativeHost] Warning: No HMAC secret found. Signature verification disabled.\n")


def verify_command_signature(command: dict[str, Any]) -> bool:
    """Verify HMAC-SHA256 signature of incoming command."""
    if SECRET_KEY is None:
        # No secret configured, allow (backward compatibility or first-time setup)
        return True
    
    if "signature" not in command:
        sys.stderr.write("[NativeHost] Rejected: Missing signature\n")
        return False
    
    provided_sig = command.pop("signature")
    
    # Recreate signature from command payload (without signature field)
    canonical = json.dumps(command, sort_keys=True).encode('utf-8')
    expected_sig = hmac.new(SECRET_KEY, canonical, hashlib.sha256).hexdigest()
    
    if not hmac.compare_digest(provided_sig, expected_sig):
        sys.stderr.write(f"[NativeHost] Rejected: Invalid signature\n")
        return False
    
    return True


def sanitize_error_message(error_msg: str) -> str:
    """Sanitize error messages to prevent internal path leakage."""
    import re
    # Remove absolute paths (Windows and Unix style)
    sanitized = re.sub(r'[A-Za-z]:\\[^\'"\s]+', '<path>', error_msg)
    sanitized = re.sub(r'/[^\'"\s]+/[^\'"\s]+', '<path>', sanitized)
    # Remove file references with line numbers
    sanitized = re.sub(r'File "[^"]+", line \d+', 'File <path>', sanitized)
    return sanitized


class NativeHost:
    def __init__(self) -> None:
        self._write_lock = threading.Lock()
        self._runner_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._current_proc: subprocess.Popen[str] | None = None
        self._running = False
        self._run_id: str | None = None
        self._current_stage: str | None = None
        self._last_progress: dict[str, Any] | None = None
        self._started_at: str | None = None

    def _write_message(self, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        with self._write_lock:
            sys.stdout.buffer.write(struct.pack("<I", len(encoded)))
            sys.stdout.buffer.write(encoded)
            sys.stdout.buffer.flush()

    def _read_message(self) -> dict[str, Any] | None:
        raw_len = sys.stdin.buffer.read(4)
        if len(raw_len) == 0:
            return None
        if len(raw_len) < 4:
            return None
        length = struct.unpack("<I", raw_len)[0]
        raw_body = sys.stdin.buffer.read(length)
        if len(raw_body) != length:
            return None
        try:
            return json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            return {"command": "invalid", "error": "Invalid JSON"}

    def _send_status(self, status: str, message: str | None = None, stage: str | None = None) -> None:
        payload: dict[str, Any] = {"type": "status", "status": status, "ts": time.time()}
        if self._run_id:
            payload["runId"] = self._run_id
        if message:
            payload["message"] = message
        if stage:
            payload["stage"] = stage
        self._write_message(payload)

    def _run_script(self, script_name: str) -> tuple[int, str]:
        script_path = SCRIPTS_DIR / script_name
        if not script_path.exists():
            return 1, f"Script not found: {script_name}"

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        command = [sys.executable, "-u", str(script_path)]
        self._current_proc = subprocess.Popen(
            command,
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=0,
            env=env,
        )

        combined_lines: list[str] = []
        assert self._current_proc.stdout is not None
        
        # Use iter() for truly line-by-line reading with immediate processing
        for line in iter(self._current_proc.stdout.readline, ''):
            if self._stop_event.is_set() and self._current_proc.poll() is None:
                self._current_proc.terminate()
                break
            
            if not line:
                if self._current_proc.poll() is not None:
                    break
                continue
            
            msg = line.rstrip()
            sys.stderr.write(f"[NativeHost DEBUG] Line received: {msg[:100]}\n")
            sys.stderr.flush()
            
            if msg.startswith(PROGRESS_PREFIX):
                sys.stderr.write(f"[NativeHost DEBUG] Progress prefix detected!\n")
                sys.stderr.flush()
                progress_raw = msg[len(PROGRESS_PREFIX):].strip()
                try:
                    progress_payload = json.loads(progress_raw)
                    if isinstance(progress_payload, dict):
                        progress_payload["type"] = "progress"
                        progress_payload["ts"] = time.time()
                        if self._run_id:
                            progress_payload["runId"] = self._run_id
                        self._last_progress = progress_payload.copy()
                        sys.stderr.write(f"[NativeHost DEBUG] Sending progress to extension\n")
                        sys.stderr.flush()
                        self._write_message(progress_payload)
                    continue
                except json.JSONDecodeError as e:
                    sys.stderr.write(f"[NativeHost DEBUG] JSON parse error: {e}\n")
                    sys.stderr.flush()
                    combined_lines.append(msg)
                    self._write_message({"type": "log", "message": msg})
                    continue
            
            combined_lines.append(msg)
            self._write_message({"type": "log", "message": msg})
        
        # Ensure process has finished
        rc = self._current_proc.wait() if self._current_proc.poll() is None else self._current_proc.returncode
        self._current_proc = None
        return rc or 0, "\n".join(combined_lines)

    def _run_pipeline(self, mode: str, stage: str | None) -> None:
        try:
            self._running = True
            self._stop_event.clear()
            self._run_id = str(uuid.uuid4())
            self._started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            self._last_progress = None

            if mode == "stage":
                if not stage:
                    self._write_message({"type": "error", "error": "Missing stage for stage mode", "ts": time.time()})
                    return
                stages = [stage]
            else:
                stages = PIPELINE_STAGES

            self._send_status("running", message="Audit run started")

            for stage_name in stages:
                if self._stop_event.is_set():
                    self._write_message({"type": "error", "error": "Audit run stopped by user", "ts": time.time(), "runId": self._run_id})
                    return

                self._current_stage = stage_name
                self._send_status("running", message=f"Running {stage_name}", stage=stage_name)
                self._write_message({"type": "stage_start", "stage": stage_name, "ts": time.time(), "runId": self._run_id})
                rc, output = self._run_script(stage_name)
                if rc != 0:
                    self._write_message({
                        "type": "error",
                        "error": f"Stage failed: {stage_name}",
                        "stage": stage_name,
                        "output": output,
                        "ts": time.time(),
                        "runId": self._run_id,
                    })
                    return
                self._write_message({"type": "stage_complete", "stage": stage_name, "ts": time.time(), "runId": self._run_id})

            self._write_message({
                "type": "complete",
                "message": "Audit pipeline completed",
                "runId": self._run_id,
                "ts": time.time(),
                "result": {
                    "mode": mode,
                    "stage": stage,
                    "reports": {
                        "xlsx": str(ROOT / "reports" / "citizens_dam_audit.xlsx"),
                        "html": str(ROOT / "reports" / "audit_report.html"),
                    },
                },
            })
        except Exception as err:  # pragma: no cover
            sanitized_msg = sanitize_error_message(str(err))
            self._write_message({"type": "error", "error": sanitized_msg, "ts": time.time(), "runId": self._run_id})
        finally:
            self._running = False
            self._run_id = None
            self._current_stage = None
            self._last_progress = None
            self._started_at = None
            self._stop_event.clear()
            self._current_proc = None

    def _handle_run(self, mode: str, stage: str | None) -> None:
        if self._running:
            self._write_message({"type": "error", "error": "Audit already running", "ts": time.time()})
            return
        self._runner_thread = threading.Thread(target=self._run_pipeline, args=(mode, stage), daemon=True)
        self._runner_thread.start()

    def _handle_stop(self) -> None:
        if not self._running:
            self._write_message({"type": "status", "status": "idle", "message": "No running audit", "ts": time.time()})
            return
        self._stop_event.set()
        self._write_message({"type": "status", "status": "stopping", "message": "Stop requested", "ts": time.time(), "runId": self._run_id})

    def serve(self) -> None:
        while True:
            message = self._read_message()
            if message is None:
                break

            # Verify HMAC signature before processing command
            if not verify_command_signature(message):
                self._write_message({
                    "type": "error",
                    "error": "Invalid or missing command signature",
                    "ts": time.time()
                })
                continue

            command = message.get("command")
            if command == "run":
                mode = message.get("mode") or "pipeline"
                stage = message.get("stage")
                self._handle_run(mode, stage)
                continue

            if command == "stop":
                self._handle_stop()
                continue

            if command == "status":
                payload: dict[str, Any] = {
                    "type": "status",
                    "status": "running" if self._running else "idle",
                    "ts": time.time(),
                }
                if self._running and self._run_id:
                    payload["runId"] = self._run_id
                    payload["stage"] = self._current_stage
                    payload["startedAt"] = self._started_at
                    if self._last_progress:
                        payload["progress"] = self._last_progress
                self._write_message(payload)
                continue

            self._write_message({"type": "error", "error": f"Unsupported command: {command}", "ts": time.time()})


def main() -> None:
    host = NativeHost()
    host.serve()


if __name__ == "__main__":
    main()
