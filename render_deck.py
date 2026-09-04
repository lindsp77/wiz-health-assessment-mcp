#!/usr/bin/env python3
"""
Standalone CSV -> PPTX renderer for the MCP-native Wiz Health Assessment.
================================================================================
This is the ONLY code in the MCP-native skill. There is NO service account, NO
Wiz GraphQL client, and NO data-collection layer here — the *agent* gathers all
metrics from the Wiz MCP and writes them to a CSV (see SKILL.md + docs/MCP_TOKEN_MAP.md).
This script only turns that CSV into the branded deck. Pure Python standard
library — nothing to install.

Usage:
  python3 render_deck.py --input-csv output/my_metrics.csv --format pptx --customer "Acme"

The CSV must have columns: Category,Variable,Title,Value,Slide,Description
(Variable as {{TOKEN}}; produced by the MCP skill.) Cells marked "Not available via MCP"
render as a compact "N/A" on the slide.
"""

import argparse
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))

from csv_metrics_processor import load_metrics_from_csv, export_metrics_to_csv, extract_template_tokens  # noqa: E402
from pptx_processor import process_pptx_template  # noqa: E402

TEMPLATE = ROOT / "templates" / "wiz_health_assessment_template.pptx"
PREVIEW_BULLET_KEYS = (
    "ALL_NON_BILLABLE_PREVIEW", "BILLABLE_ADVANCED", "BILLABLE_CODE", "BILLABLE_DEFEND",
    "BILLABLE_SENSOR", "PRIVATE_BILLABLE", "PRIVATE_NON_BILLABLE",
)


def main():
    ap = argparse.ArgumentParser(description="MCP-native Wiz Health Assessment: CSV -> PPTX")
    ap.add_argument("--input-csv", "-i", required=True, help="MCP-collected metrics CSV")
    ap.add_argument("--format", choices=["pptx", "csv"], default="pptx")
    ap.add_argument("--customer", "-c", default="Customer")
    ap.add_argument("--template", default=str(TEMPLATE))
    ap.add_argument("--output-pptx")
    args = ap.parse_args()

    slug = re.sub(r"[^A-Za-z0-9_-]", "_", args.customer)
    out_dir = Path.cwd() / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    output_pptx = args.output_pptx or str(out_dir / f"Wiz_Health_Assessment_{slug}_MCP.pptx")

    print(f"[*] Loading MCP metrics CSV: {args.input_csv}")
    merged = load_metrics_from_csv(args.input_csv)

    # Option-2: a metric the MCP can't read is "Not available via MCP" in the CSV (for the TAM);
    # on the slide, render it as a compact "N/A" so cells stay clean.
    for v in merged.values():
        if str(v.get("value", "")).strip() == "Not available via MCP":
            v["value"] = "N/A"

    if args.format == "csv":
        tmpl_tokens = extract_template_tokens(args.template) or None
        out = export_metrics_to_csv(merged, str(out_dir / f"Wiz_Health_Assessment_{slug}_MCP_metrics.csv"),
                                    args.customer, template_tokens=tmpl_tokens)
        print(f"[✓] CSV written: {out}")
        return

    # Preview highlighting: enabled features come through as bullet-list tokens.
    enabled_titles = set()
    for pk in PREVIEW_BULLET_KEYS:
        val = str((merged.get(pk) or {}).get("value", ""))
        for line in re.split(r"[\n;]", val):
            t = line.strip().lstrip("•").strip()
            if t and t != "N/A":
                enabled_titles.add(t)

    if not os.path.exists(args.template):
        sys.exit(f"[!] Template not found: {args.template}")

    print(f"[*] Rendering PPTX from {args.template}")
    res = process_pptx_template(template_path=args.template, output_path=output_pptx,
                                variables=merged, enabled_preview_titles=enabled_titles)
    print(f"[✓] PPTX: {output_pptx} ({res['file_size']} bytes; {res['replacements_made']} replacements)")


if __name__ == "__main__":
    main()
