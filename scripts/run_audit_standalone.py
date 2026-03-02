#!/usr/bin/env python3
"""
Standalone orchestrator for the Aprimo DAM audit pipeline.

Runs all audit stages in sequence without requiring the Chrome extension.
Progress is printed to stdout and optionally written to a log file.

Usage:
    python scripts/run_audit_standalone.py [--log-file PATH]

Stages:
    01_crawl_citizens_images.py      - Crawl citizensbank.com for images
    02_build_dam_fingerprints.py     - Build DAM asset fingerprints
    03_build_citizens_fingerprints.py - Build Citizens site fingerprints
    04_match_assets.py               - Match assets between DAM and site
    05_build_reports.py              - Generate audit reports
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import sys
import time
from pathlib import Path

# Root directory is one level up from scripts/
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
OUTPUT_DIR = ROOT / "assets" / "audit"
STATUS_FILE = OUTPUT_DIR / "pipeline_status.json"

PIPELINE_STAGES = [
    "01_crawl_citizens_images.py",
    "02_build_dam_fingerprints.py",
    "03_build_citizens_fingerprints.py",
    "04_match_assets.py",
    "05_build_reports.py",
]


class PipelineStatus:
    """Manages persistent status file for external monitoring."""
    
    def __init__(self, status_file: Path):
        self.status_file = status_file
        self.status_file.parent.mkdir(parents=True, exist_ok=True)
        
        self.state = {
            "current_stage": None,
            "current_stage_num": 0,
            "total_stages": len(PIPELINE_STAGES),
            "pipeline_percent": 0.0,
            "started_at": None,
            "updated_at": None,
            "status": "idle",  # idle | running | completed | error
            "stages": {}
        }
        
        # Initialize all stages as pending
        for stage in PIPELINE_STAGES:
            self.state["stages"][stage] = {"status": "pending"}
        
        self.write()
    
    def write(self) -> None:
        """Write current state to JSON file."""
        self.state["updated_at"] = time.time()
        try:
            self.status_file.write_text(json.dumps(self.state, indent=2, ensure_ascii=False))
        except Exception as err:
            # Don't crash pipeline if status file write fails
            print(f"WARNING: Failed to write status file: {err}", file=sys.stderr)
    
    def start_pipeline(self) -> None:
        """Mark pipeline as started."""
        self.state["status"] = "running"
        self.state["started_at"] = time.time()
        self.write()
    
    def start_stage(self, stage_name: str, stage_num: int) -> None:
        """Mark stage as started."""
        self.state["current_stage"] = stage_name
        self.state["current_stage_num"] = stage_num
        self.state["pipeline_percent"] = ((stage_num - 1) / self.state["total_stages"]) * 100
        self.state["stages"][stage_name] = {
            "status": "running",
            "started_at": time.time(),
            "last_progress": None
        }
        self.write()
    
    def update_stage_progress(self, stage_name: str, progress: dict) -> None:
        """Update progress for current stage."""
        if stage_name in self.state["stages"]:
            self.state["stages"][stage_name]["last_progress"] = progress
            self.write()
    
    def complete_stage(self, stage_name: str, return_code: int, duration: float) -> None:
        """Mark stage as completed or failed."""
        if stage_name in self.state["stages"]:
            stage_data = self.state["stages"][stage_name]
            stage_data["status"] = "completed" if return_code == 0 else "error"
            stage_data["completed_at"] = time.time()
            stage_data["duration_seconds"] = duration
            stage_data["exit_code"] = return_code
            
            # Update pipeline percent
            completed_count = sum(1 for s in self.state["stages"].values() if s["status"] == "completed")
            self.state["pipeline_percent"] = (completed_count / self.state["total_stages"]) * 100
            
            self.write()
    
    def complete_pipeline(self, success: bool) -> None:
        """Mark pipeline as completed or failed."""
        self.state["status"] = "completed" if success else "error"
        self.state["completed_at"] = time.time()
        self.state["pipeline_percent"] = 100.0 if success else self.state["pipeline_percent"]
        self.write()


class AuditOrchestrator:
    def __init__(self, log_file: Path | None = None, status_file: Path = STATUS_FILE):
        self.log_file = log_file
        self.status_file = status_file
        self.logger = self._setup_logger()
        self.start_time = time.time()
        self.pipeline_status = PipelineStatus(status_file)

    def _setup_logger(self) -> logging.Logger:
        """Configure logger for stdout and optional file output."""
        logger = logging.getLogger("audit_orchestrator")
        logger.setLevel(logging.INFO)
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
        
        # File handler (optional)
        if self.log_file:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(self.log_file, mode="w", encoding="utf-8")
            file_handler.setLevel(logging.INFO)
            file_handler.setFormatter(console_formatter)
            logger.addHandler(file_handler)
        
        return logger

    def _parse_audit_progress(self, line: str) -> dict | None:
        """Parse AUDIT_PROGRESS JSON from script output."""
        match = re.search(r"AUDIT_PROGRESS\s+({.*})", line)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        return None
    
    def _render_progress_bar(self, progress: dict) -> str:
        """Render inline progress bar from progress data."""
        current = progress.get("current") or progress.get("urls_completed", 0)
        total = progress.get("total") or progress.get("urls_total", 0)
        
        if not total or total == 0:
            return ""
        
        percent = (current / total) * 100
        bar_width = 40
        filled = int((percent / 100) * bar_width)
        bar = "█" * filled + "░" * (bar_width - filled)
        
        # Build status text
        status_parts = [f"{current}/{total}"]
        
        if "images_detected" in progress:
            status_parts.append(f"{progress['images_detected']} images")
        
        if "images_remaining" in progress and progress["images_remaining"] > 0:
            status_parts.append(f"{progress['images_remaining']} pending")
        
        status_text = " | ".join(status_parts)
        
        return f"  └─ [{bar}] {percent:>5.1f}% | {status_text}"

    def run_stage(self, script_name: str, stage_num: int) -> tuple[int, float]:
        """
        Run a single audit stage script with live progress monitoring.
        
        Returns:
            (return_code, duration_seconds)
        """
        script_path = SCRIPTS_DIR / script_name
        
        if not script_path.exists():
            self.logger.error(f"Script not found: {script_path}")
            self.pipeline_status.complete_stage(script_name, 1, 0.0)
            return 1, 0.0
        
        pipeline_pct = ((stage_num - 1) / len(PIPELINE_STAGES)) * 100
        self.logger.info("=" * 80)
        self.logger.info(f"[{stage_num}/{len(PIPELINE_STAGES)}] {script_name} | Pipeline: {pipeline_pct:.0f}%")
        self.logger.info("=" * 80)
        
        self.pipeline_status.start_stage(script_name, stage_num)
        stage_start = time.time()
        last_progress = None
        last_progress_line = None
        
        try:
            process = subprocess.Popen(
                [sys.executable, "-u", str(script_path)],
                cwd=str(ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                encoding="utf-8",
                errors="replace"
            )
            
            # Read output line by line
            assert process.stdout is not None
            for line in iter(process.stdout.readline, ""):
                if not line:
                    break
                
                # Parse AUDIT_PROGRESS lines
                progress = self._parse_audit_progress(line)
                if progress:
                    last_progress = progress
                    self.pipeline_status.update_stage_progress(script_name, progress)
                    
                    # Render progress bar on same line
                    progress_line = self._render_progress_bar(progress)
                    if progress_line:
                        # Clear previous progress line if exists
                        if last_progress_line:
                            print("\r" + " " * len(last_progress_line) + "\r", end="", flush=True)
                        print(progress_line, end="", flush=True)
                        last_progress_line = progress_line
                    continue
                
                # Print other output normally
                # If we had a progress bar, move to new line first
                if last_progress_line:
                    print()  # New line after progress bar
                    last_progress_line = None
                
                print(line, end="", flush=True)
            
            # Final newline after progress bar if it was last thing shown
            if last_progress_line:
                print()
            
            process.wait()
            return_code = process.returncode
            duration = time.time() - stage_start
            
            self.pipeline_status.complete_stage(script_name, return_code, duration)
            
            if return_code != 0:
                self.logger.error(
                    f"❌ {script_name} FAILED with exit code {return_code} "
                    f"(duration: {duration:.1f}s)"
                )
                return return_code, duration
            
            self.logger.info(f"✅ {script_name} completed successfully (duration: {duration:.1f}s)")
            
            # Show final progress if available
            if last_progress:
                self.logger.info(f"   Final: {last_progress.get('current', 0)}/{last_progress.get('total', 0)} items processed")
            
            return 0, duration
            
        except Exception as err:
            duration = time.time() - stage_start
            self.logger.error(f"❌ {script_name} raised exception: {err} (duration: {duration:.1f}s)")
            self.pipeline_status.complete_stage(script_name, 1, duration)
            return 1, duration

    def run_pipeline(self) -> int:
        """
        Run all pipeline stages in sequence.
        
        Returns:
            Exit code (0 = success, non-zero = failure)
        """
        self.logger.info("🚀 Starting Aprimo DAM Audit Pipeline (Standalone Mode)")
        self.logger.info(f"Root directory: {ROOT}")
        self.logger.info(f"Total stages: {len(PIPELINE_STAGES)}")
        if self.log_file:
            self.logger.info(f"Log file: {self.log_file}")
        self.logger.info(f"Status file: {self.status_file}")
        self.logger.info("")
        
        self.pipeline_status.start_pipeline()
        stage_results: list[tuple[str, int, float]] = []
        
        for idx, stage_name in enumerate(PIPELINE_STAGES, start=1):
            return_code, duration = self.run_stage(stage_name, idx)
            stage_results.append((stage_name, return_code, duration))
            
            if return_code != 0:
                self.logger.error(f"\n⛔ Pipeline aborted at stage {idx}/{len(PIPELINE_STAGES)}")
                self.pipeline_status.complete_pipeline(success=False)
                self._print_summary(stage_results, success=False)
                return return_code
            
            self.logger.info("")
        
        self.pipeline_status.complete_pipeline(success=True)
        self._print_summary(stage_results, success=True)
        return 0

    def _print_summary(self, stage_results: list[tuple[str, int, float]], success: bool) -> None:
        """Print final pipeline summary."""
        total_duration = time.time() - self.start_time
        
        self.logger.info("=" * 80)
        self.logger.info("PIPELINE SUMMARY")
        self.logger.info("=" * 80)
        
        for stage_name, return_code, duration in stage_results:
            status = "✅ SUCCESS" if return_code == 0 else f"❌ FAILED (code {return_code})"
            self.logger.info(f"  {stage_name:<40} {status:<20} {duration:>6.1f}s")
        
        self.logger.info("-" * 80)
        self.logger.info(f"Total pipeline duration: {total_duration:.1f}s")
        
        if success:
            self.logger.info("🎉 AUDIT PIPELINE COMPLETED SUCCESSFULLY")
            self.logger.info(f"\nReports generated:")
            self.logger.info(f"  - Excel: {ROOT / 'reports' / 'citizens_dam_audit.xlsx'}")
            self.logger.info(f"  - HTML:  {ROOT / 'reports' / 'audit_report.html'}")
        else:
            failed_count = sum(1 for _, rc, _ in stage_results if rc != 0)
            self.logger.error(f"❌ PIPELINE FAILED ({failed_count} stage(s) failed)")
        
        self.logger.info("=" * 80)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Aprimo DAM audit pipeline in standalone mode (no Chrome extension required).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=None,
        help="Optional log file path (in addition to stdout). Default: no file logging.",
    )
    parser.add_argument(
        "--status-file",
        type=Path,
        default=STATUS_FILE,
        help=f"Path to persistent status JSON file for external monitoring. Default: {STATUS_FILE}",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    orchestrator = AuditOrchestrator(log_file=args.log_file, status_file=args.status_file)
    return orchestrator.run_pipeline()


if __name__ == "__main__":
    sys.exit(main())
