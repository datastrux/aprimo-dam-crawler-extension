from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
AUDIT_DIR = ROOT / "assets" / "audit"
REPORTS_DIR = ROOT / "reports"

STAGES = [
    "01_crawl_citizens_images.py",
    "02_build_dam_fingerprints.py",
    "03_build_citizens_fingerprints.py",
    "04_match_assets.py",
    "05_build_reports.py",
]

# Output files that indicate stage completion
STAGE_OUTPUTS = {
    "01_crawl_citizens_images.py": AUDIT_DIR / "citizens_images.json",
    "02_build_dam_fingerprints.py": AUDIT_DIR / "dam_fingerprints.json",
    "03_build_citizens_fingerprints.py": AUDIT_DIR / "citizens_fingerprints.json",
    "04_match_assets.py": AUDIT_DIR / "match_results.json",
    "05_build_reports.py": REPORTS_DIR / "audit_report.html",
}


def detect_completed_stages() -> int:
    """Detect which stages have completed by checking for output files.
    
    Returns:
        Index of first incomplete stage (0-based), or len(STAGES) if all complete
    """
    for i, stage in enumerate(STAGES):
        output_file = STAGE_OUTPUTS.get(stage)
        if not output_file or not output_file.exists():
            return i
    return len(STAGES)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the complete audit pipeline")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from where the pipeline failed (skip completed stages)"
    )
    parser.add_argument(
        "--start-from",
        type=int,
        choices=range(1, len(STAGES) + 1),
        metavar="STAGE",
        help=f"Start from stage number (1-{len(STAGES)})"
    )
    args = parser.parse_args()

    # Determine starting stage
    start_idx = 0
    if args.start_from:
        start_idx = args.start_from - 1
        print(f"\n=== Starting from stage {args.start_from}: {STAGES[start_idx]} ===")
    elif args.resume:
        start_idx = detect_completed_stages()
        if start_idx >= len(STAGES):
            print("\nAll stages already complete. Use --start-from to re-run specific stages.")
            print("Open reports/audit_report.html and reports/citizens_dam_audit.xlsx")
            return
        print(f"\n=== Resuming from stage {start_idx + 1}: {STAGES[start_idx]} ===")
        print(f"Skipped {start_idx} completed stage(s)\n")

    python = sys.executable
    for idx in range(start_idx, len(STAGES)):
        stage = STAGES[idx]
        script_path = SCRIPTS_DIR / stage
        print(f"\n=== Running stage {idx + 1}/{len(STAGES)}: {stage} ===")
        completed = subprocess.run([python, str(script_path)], cwd=str(ROOT))
        if completed.returncode != 0:
            print(f"\n❌ Stage {idx + 1} failed: {stage}")
            print(f"To resume from this stage, run: python scripts/run_audit_pipeline.py --start-from {idx + 1}")
            raise SystemExit(f"Stage failed: {stage}")

    print("\n✅ Pipeline completed successfully.")
    print("Open reports/audit_report.html and reports/citizens_dam_audit.xlsx")


if __name__ == "__main__":
    main()
