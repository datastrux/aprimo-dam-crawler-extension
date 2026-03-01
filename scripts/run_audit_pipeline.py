from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"

STAGES = [
    "01_crawl_citizens_images.py",
    "02_build_dam_fingerprints.py",
    "03_build_citizens_fingerprints.py",
    "04_match_assets.py",
    "05_build_reports.py",
]


def main() -> None:
    python = sys.executable
    for stage in STAGES:
        script_path = SCRIPTS_DIR / stage
        print(f"\n=== Running {stage} ===")
        completed = subprocess.run([python, str(script_path)], cwd=str(ROOT))
        if completed.returncode != 0:
            raise SystemExit(f"Stage failed: {stage}")

    print("\nPipeline completed successfully.")
    print("Open reports/audit_report.html and reports/citizens_dam_audit.xlsx")


if __name__ == "__main__":
    main()
