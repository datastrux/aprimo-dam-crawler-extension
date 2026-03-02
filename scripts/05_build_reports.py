from __future__ import annotations

import argparse
import json
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font

from audit_common import AUDIT_DIR, REPORTS_DIR, ensure_dirs, load_json, write_csv, write_json


def write_xlsx(summary: dict, master_rows: list[dict], unmatched_rows: list[dict], 
               dam_dupes: list[dict], citizens_dupes: list[dict], 
               governance: dict, output: Path) -> None:
    wb = Workbook()

    # Summary sheet
    ws_summary = wb.active
    ws_summary.title = "Summary"
    ws_summary.append(["Metric", "Value"])
    for key, value in summary.items():
        ws_summary.append([key, value])
    
    # Add governance metrics
    ws_summary.append(["--- Governance Metrics ---", ""])
    for key, value in governance.items():
        ws_summary.append([key, value])
    
    ws_summary["A1"].font = Font(bold=True)
    ws_summary["B1"].font = Font(bold=True)

    # Citizens Images sheet
    ws_master = wb.create_sheet("Citizens Images")
    headers = [
        "image_url",
        "match_status",
        "match_method",
        "url_contains_asset_id",
        "dam_item_id",
        "dam_file_name",
        "phash_distance",
        "page_count",
        "page_urls",
        "needs_dam_upload",
    ]
    ws_master.append(headers)
    for cell in ws_master[1]:
        cell.font = Font(bold=True)
    for row in master_rows:
        ws_master.append([row.get(h) for h in headers])

    ws_unmatched = wb.create_sheet("Needs DAM Upload")
    ws_unmatched.append(headers)
    for cell in ws_unmatched[1]:
        cell.font = Font(bold=True)
    for row in unmatched_rows:
        ws_unmatched.append([row.get(h) for h in headers])

    ws_dupes = wb.create_sheet("DAM Duplicates")
    dup_headers = ["sha256", "count", "item_ids", "file_names"]
    ws_dupes.append(dup_headers)
    for cell in ws_dupes[1]:
        cell.font = Font(bold=True)
    for row in dam_dupes:
        ws_dupes.append([
            row.get("sha256"),
            row.get("count"),
            " | ".join(row.get("item_ids", [])),
            " | ".join(row.get("file_names", [])),
        ])
    
    # Citizens Duplicates sheet (same image, multiple URLs)
    ws_citizens_dupes = wb.create_sheet("Citizens Duplicates")
    citizens_dup_headers = ["phash", "count", "image_urls", "dam_item_id", 
                           "total_page_count", "has_direct_dam_url", "has_local_copy"]
    ws_citizens_dupes.append(citizens_dup_headers)
    for cell in ws_citizens_dupes[1]:
        cell.font = Font(bold=True)
    for row in citizens_dupes:
        ws_citizens_dupes.append([
            row.get("phash"),
            row.get("count"),
            " | ".join(row.get("image_urls", [])),
            row.get("dam_item_id"),
            row.get("total_page_count"),
            "Yes" if row.get("has_direct_dam_url") else "No",
            "Yes" if row.get("has_local_copy") else "No",
        ])

    wb.save(output)


def write_html(master_rows: list[dict], output: Path) -> None:
    payload = json.dumps(master_rows, ensure_ascii=False)
    html = f"""<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Citizens vs DAM Audit Report</title>
  <style>
    body {{ font-family: Segoe UI, Arial, sans-serif; margin: 16px; }}
    .controls {{ display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }}
    input, select {{ padding: 6px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
    th, td {{ border: 1px solid #ddd; padding: 6px; vertical-align: top; }}
    th {{ background: #f3f3f3; position: sticky; top: 0; }}
    .pill {{ padding: 2px 6px; border-radius: 10px; font-size: 11px; color: #333; }}
    .match_url_direct {{ background: #c3f0ca; color: #0d5e1e; font-weight: bold; }}
    .match_exact {{ background: #dff6e7; }}
    .match_phash {{ background: #fff6dd; }}
    .unmatched {{ background: #fde8e8; }}
    .badge {{ padding: 2px 4px; background: #e0e0e0; border-radius: 3px; font-size: 10px; }}
    .badge-dam {{ background: #c3f0ca; color: #0d5e1e; }}
    .badge-local {{ background: #fff6dd; }}
  </style>
</head>
<body>
  <h2>Citizens vs DAM Audit</h2>
  <div class=\"controls\">
    <input id=\"q\" placeholder=\"Search image URL or DAM item\" style=\"min-width:320px\" />
    <select id=\"status\">
      <option value=\"\">All statuses</option>
      <option value=\"match_url_direct\">match_url_direct (Direct DAM)</option>
      <option value=\"match_exact\">match_exact</option>
      <option value=\"match_phash\">match_phash</option>
      <option value=\"unmatched\">unmatched</option>
      <option value=\"unmatched_error\">unmatched_error</option>
    </select>
    <select id=\"urlType\">
      <option value=\"\">All URL types</option>
      <option value=\"direct_dam\">Direct DAM URLs</option>
      <option value=\"local_copy\">Local Copies</option>
    </select>
    <label><input type=\"checkbox\" id=\"needs\" /> Needs DAM Upload only</label>
  </div>
  <div id=\"count\"></div>
  <table>
    <thead>
      <tr>
        <th>image_url</th>
        <th>status</th>
        <th>URL Type</th>
        <th>dam_item_id</th>
        <th>dam_file_name</th>
        <th>phash_distance</th>
        <th>page_count</th>
        <th>page_urls</th>
      </tr>
    </thead>
    <tbody id=\"rows\"></tbody>
  </table>
  <script>
    const DATA = {payload};
    const rowsEl = document.getElementById('rows');
    const countEl = document.getElementById('count');
    const qEl = document.getElementById('q');
    const statusEl = document.getElementById('status');
    const urlTypeEl = document.getElementById('urlType');
    const needsEl = document.getElementById('needs');

    function render() {{
      const q = qEl.value.toLowerCase().trim();
      const status = statusEl.value;
      const urlType = urlTypeEl.value;
      const needsOnly = needsEl.checked;

      const filtered = DATA.filter(r => {{
        if (status && r.match_status !== status) return false;
        if (urlType === 'direct_dam' && !r.url_contains_asset_id) return false;
        if (urlType === 'local_copy' && r.url_contains_asset_id) return false;
        if (needsOnly && !r.needs_dam_upload) return false;
        if (!q) return true;
        return [r.image_url, r.dam_item_id, r.dam_file_name, r.page_urls].join(' ').toLowerCase().includes(q);
      }});

      rowsEl.innerHTML = filtered.map(r => {{
        const urlBadge = r.url_contains_asset_id 
          ? '<span class=\"badge badge-dam\">DAM URL</span>' 
          : '<span class=\"badge badge-local\">Local</span>';
        
        return `
        <tr>
          <td><a href=\"${{r.image_url}}\" target=\"_blank\">${{r.image_url}}</a></td>
          <td><span class=\"pill ${{r.match_status}}\">${{r.match_status}}</span></td>
          <td>${{urlBadge}}</td>
          <td>${{r.dam_item_id || ''}}</td>
          <td>${{r.dam_file_name || ''}}</td>
          <td>${{r.phash_distance ?? ''}}</td>
          <td>${{r.page_count ?? ''}}</td>
          <td>${{(r.page_urls || '').toString().replace(/\|/g, '<br/>')}}</td>
        </tr>
      `}}).join('');

      countEl.textContent = `Rows: ${{filtered.length}} / ${{DATA.length}}`;
    }}

    qEl.addEventListener('input', render);
    statusEl.addEventListener('change', render);
    urlTypeEl.addEventListener('change', render);
    needsEl.addEventListener('change', render);
    render();
  </script>
</body>
</html>"""
    output.write_text(html, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build final CSV/XLSX/HTML audit reports")
    parser.add_argument("--matches", type=Path, default=AUDIT_DIR / "match_results.json")
    parser.add_argument("--unmatched", type=Path, default=AUDIT_DIR / "unmatched_results.json")
    parser.add_argument("--dam-dupes", type=Path, default=AUDIT_DIR / "dam_internal_dupes.json")
    parser.add_argument("--citizens-dupes", type=Path, default=AUDIT_DIR / "citizens_duplicates.json")
    parser.add_argument("--governance", type=Path, default=AUDIT_DIR / "governance_metrics.json")
    args = parser.parse_args()

    ensure_dirs()
    matches = load_json(args.matches)
    unmatched = load_json(args.unmatched)
    dam_dupes = load_json(args.dam_dupes)
    
    # Load new governance data (may not exist in older runs)
    try:
        citizens_dupes = load_json(args.citizens_dupes)
    except FileNotFoundError:
        citizens_dupes = []
    
    try:
        governance = load_json(args.governance)
    except FileNotFoundError:
        governance = {}

    master_rows: list[dict] = []
    for row in matches:
        out = dict(row)
        out["needs_dam_upload"] = False
        out["page_urls"] = "|".join(out.get("page_urls", []))
        master_rows.append(out)
    for row in unmatched:
        out = dict(row)
        out["needs_dam_upload"] = out.get("match_status") in {"unmatched", "unmatched_error"}
        out["page_urls"] = "|".join(out.get("page_urls", []))
        master_rows.append(out)

    summary = {
        "citizens_images_total": len(master_rows),
        "matched_url_direct": sum(1 for r in master_rows if r.get("match_status") == "match_url_direct"),
        "matched_exact": sum(1 for r in master_rows if r.get("match_status") == "match_exact"),
        "matched_phash": sum(1 for r in master_rows if r.get("match_status") == "match_phash"),
        "unmatched": sum(1 for r in master_rows if r.get("match_status") in {"unmatched", "unmatched_error"}),
        "needs_dam_upload": sum(1 for r in master_rows if r.get("needs_dam_upload")),
        "dam_internal_dupe_groups": len(dam_dupes),
        "citizens_duplicate_groups": len(citizens_dupes),
    }

    master_csv = AUDIT_DIR / "audit_master.csv"
    write_csv(
        master_csv,
        master_rows,
        ["image_url", "match_status", "match_method", "url_contains_asset_id", "dam_item_id", "dam_file_name", "phash_distance", "page_count", "page_urls", "needs_dam_upload"],
    )
    write_json(AUDIT_DIR / "audit_master.json", master_rows)
    write_json(AUDIT_DIR / "audit_summary.json", summary)

    xlsx_out = REPORTS_DIR / "citizens_dam_audit.xlsx"
    html_out = REPORTS_DIR / "audit_report.html"

    unmatched_rows = [r for r in master_rows if r.get("needs_dam_upload")]
    write_xlsx(summary, master_rows, unmatched_rows, dam_dupes, citizens_dupes, governance, xlsx_out)
    write_html(master_rows, html_out)

    print(json.dumps({
        "summary": summary,
        "governance": governance,
        "outputs": {
            "master_csv": str(master_csv),
            "master_json": str(AUDIT_DIR / "audit_master.json"),
            "summary_json": str(AUDIT_DIR / "audit_summary.json"),
            "xlsx": str(xlsx_out),
            "html": str(html_out),
        },
    }, indent=2))


if __name__ == "__main__":
    main()
