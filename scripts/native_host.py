from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
import threading
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


class NativeHost:
    def __init__(self) -> None:
        self._write_lock = threading.Lock()
        self._runner_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._current_proc: subprocess.Popen[str] | None = None
        self._running = False

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
        payload: dict[str, Any] = {"type": "status", "status": status}
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
        command = [sys.executable, str(script_path)]
        self._current_proc = subprocess.Popen(
            command,
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        combined_lines: list[str] = []
        assert self._current_proc.stdout is not None
        while True:
            if self._stop_event.is_set() and self._current_proc.poll() is None:
                self._current_proc.terminate()
            line = self._current_proc.stdout.readline()
            if line:
                msg = line.rstrip()
                if msg.startswith(PROGRESS_PREFIX):
                    progress_raw = msg[len(PROGRESS_PREFIX):].strip()
                    try:
                        progress_payload = json.loads(progress_raw)
                    except json.JSONDecodeError:
                        combined_lines.append(msg)
                        self._write_message({"type": "log", "message": msg})
                    else:
                        if isinstance(progress_payload, dict):
                            progress_payload["type"] = "progress"
                            self._write_message(progress_payload)
                        continue
                combined_lines.append(msg)
                self._write_message({"type": "log", "message": msg})
            if self._current_proc.poll() is not None:
                break
        rc = self._current_proc.returncode or 0
        self._current_proc = None
        return rc, "\n".join(combined_lines)

    def _run_pipeline(self, mode: str, stage: str | None) -> None:
        try:
            self._running = True
            self._stop_event.clear()

            if mode == "stage":
                if not stage:
                    self._write_message({"type": "error", "error": "Missing stage for stage mode"})
                    return
                stages = [stage]
            else:
                stages = PIPELINE_STAGES

            self._send_status("running", message="Audit run started")

            for stage_name in stages:
                if self._stop_event.is_set():
                    self._write_message({"type": "error", "error": "Audit run stopped by user"})
                    return

                self._send_status("running", message=f"Running {stage_name}", stage=stage_name)
                self._write_message({"type": "stage_start", "stage": stage_name})
                rc, output = self._run_script(stage_name)
                if rc != 0:
                    self._write_message({
                        "type": "error",
                        "error": f"Stage failed: {stage_name}",
                        "stage": stage_name,
                        "output": output,
                    })
                    return
                self._write_message({"type": "stage_complete", "stage": stage_name})

            self._write_message({
                "type": "complete",
                "message": "Audit pipeline completed",
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
            self._write_message({"type": "error", "error": str(err)})
        finally:
            self._running = False
            self._stop_event.clear()
            self._current_proc = None

    def _handle_run(self, mode: str, stage: str | None) -> None:
        if self._running:
            self._write_message({"type": "error", "error": "Audit already running"})
            return
        self._runner_thread = threading.Thread(target=self._run_pipeline, args=(mode, stage), daemon=True)
        self._runner_thread.start()

    def _handle_stop(self) -> None:
        if not self._running:
            self._write_message({"type": "status", "status": "idle", "message": "No running audit"})
            return
        self._stop_event.set()
        self._write_message({"type": "status", "status": "stopping", "message": "Stop requested"})

    def serve(self) -> None:
        while True:
            message = self._read_message()
            if message is None:
                break

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
                self._write_message({"type": "status", "status": "running" if self._running else "idle"})
                continue

            self._write_message({"type": "error", "error": f"Unsupported command: {command}"})


def main() -> None:
    host = NativeHost()
    host.serve()


if __name__ == "__main__":
    main()
