---
name: wiz-health-assessment-mcp
description: >-
  Generate a Wiz Tenant Health Assessment (metrics CSV + branded PPTX deck) using ONLY the
  Wiz MCP server — browser-OAuth, no service account, no data-collection script. The agent calls
  the MCP's curated domain tools + Security-Graph, maps each result to the deck's template
  variables, marks anything the MCP cannot supply as "Not available via MCP", writes the CSV, and
  renders the deck with the bundled offline renderer. Use when a customer wants the assessment
  without minting a Wiz service account.
---

# Wiz Health Assessment — MCP-Native

You are a Wiz cloud-security advisor. This skill produces the **Wiz Tenant Health Assessment**
using **only the Wiz MCP** — no service account, no `.env` secrets, no data-collection Python.
You (the agent) call the MCP tools directly, map their results to the deck's `{{TOKEN}}` variables,
write a CSV, and render the deck with the bundled offline renderer (`render_deck.py`).

> **Coverage.** ~60–75% of the deck's variables populate from the MCP (higher with the Security-Graph
> recoveries in `docs/MCP_TOKEN_MAP.md`). The structural gaps — the data-scanner config block
> (slide 18 `DSS_*`), most ASM/workload config toggles (slide 17), integration activity dates,
> and a few analytics — have **no MCP source** and are marked **`Not available via MCP`** (rendered
> as "N/A"). See `docs/MCP_ONLY_COVERAGE.md`.

---

## 🔒 Security
- **Never** ask for or handle a Wiz Client Secret, API token, or any credential. The Wiz MCP
  authenticates via its own browser-OAuth session; there is nothing to paste.
- Read-only throughout, against the tenant the connected MCP is authenticated to.

## Prerequisites
- The **Wiz MCP server must be connected** in this client — verify with
  `mcp__claude_ai_Wiz_MCP__discover` (no args). If absent, stop and tell the user to add the Wiz MCP
  integration; do not attempt any fallback.
- **No installs.** Outputs are **CSV + PPTX**, needing only **Python 3** (present in Claude Code) — the
  render pipeline is pure standard library, no `pip`/packages, nothing to install.

---

## Procedure

### Step 1 — Confirm the MCP is live
Call `mcp__claude_ai_Wiz_MCP__discover`. If it returns domains, continue.

### Step 2 — Load the variable catalog
Read `docs/DECK_VARIABLE_REFERENCE.csv` (the master list of every deck token: `Variable,Title,
Description,Slide,Category`). You will fill a `Value` column.

### Step 3 — Collect from the MCP
Execute the calls in **`docs/MCP_TOKEN_MAP.md`** via `mcp__claude_ai_Wiz_MCP__execute(tool_name, parameters)`.
**Read the map's "✅ Verified runtime corrections" section first** — it fixes the exact param shapes
(K8s `*_property_name`, `limit` vs `first`, `filter_scope:"LATEST_ISSUE_DETECTION"` for issue counts,
the `SECURITY_TOOL_SCAN` graph pattern for per-status scan splits, etc.) so calls succeed first-try.
Guidance:
- **Counts** = a filtered call's `totalCount` (request `first:1` / `limit:1`); don't page all rows.
- **Scan counts (data + workload): `execute_graph_query` on `SECURITY_TOOL_SCAN` ONLY — read
  `docs/wiz-scan-counts.md` first.** `DS_T/F/SK/P` come from `dataSource_name:["Wiz Data Scanner"]` +
  `status` splits; reconcile Success+Skipped+Error=Total before reporting; failed status is
  **`ScanStatusError`** (`ScanStatusFailed` silently returns 0). **NEVER** use `get_data_scan_results`,
  `summarize_scan_failures_by_account_region`, or `list_workload_scan_failures` — they mis-scope /
  cap / mix data+workload rows (the doc explains each). Per-status splits `RCI_*`/`VMI_*`/`NON_*` use
  the same graph pattern (map call 24).
- **Derived tokens** (percentages, `AE_TOT`, coverage) — compute per the map.
- If a call fails, record its tokens as `Not available via MCP` and continue.

### Step 4 — Mark the gaps
Every catalog token not populated in Step 3 — including the map's "NOT available via MCP" list —
gets the literal `Not available via MCP`. Do not guess or leave blank.

### Step 5 — Write the CSV
Write `output/Wiz_Health_Assessment_<Customer>_<YYYY-MM-DD>_MCP_metrics.csv` with columns
`Category,Variable,Title,Value,Slide,Description`, one row per catalog token in catalog order.

### Step 6 — Render the deck (offline; **no installs required**)
This is bundled and **dependency-free**: `render_deck.py` + `scripts/` are **pure Python standard
library** (no `pip install`, no packages) and build the PPTX by filling the bundled
`templates/wiz_health_assessment_template.pptx` directly. The only runtime need is **Python 3**, which
Claude Code already has. Do NOT install anything.

- **CSV** — always produced, zero dependencies. This is the guaranteed deliverable.
- **PPTX** — the rich deck, also **zero dependencies / no install**:
  ```bash
  python3 render_deck.py --input-csv output/<the CSV> --format pptx --customer "<Customer>"
  ```
  Cells marked `Not available via MCP` render as a compact **N/A**; scanner-config toggles keep ✓/✗.

### Step 7 — Report
Give the user the CSV + deck paths and a one-line coverage summary
(**X of N populated from MCP, Y marked "Not available via MCP"**), plus the headline gaps.

---

## Notes
- **`discover` is NOT the full tool surface, and the surface is permission-gated.** Do not conclude
  "no tool for X" from `discover` — it omits real, callable tools (e.g. `list_deployments`,
  `list_automation_rules`). And a tool absent from `execute` can be *nonexistent* OR *scope-gated*
  (Wiz: "a missing tool = a missing permission"). To settle reachability: check
  **`docs.wiz.io/docs/wiz-ai-tools`** (every MCP tool + its required **Scopes**) and
  **`docs.wiz.io/docs/graphql-scopes-to-apis`** (scope → GraphQL queries) — reachable in-session via
  the `docs` domain's `wiz_docs_knowledge_base` — then probe the exact name with `execute` to confirm.
  A tool listed on the page but absent from `execute` just needs its scope granted; a capability with
  no tool row (e.g. configured `automationWorkflows` → `F_WF`) is genuinely outside the MCP surface
  (Terraform/raw-GraphQL only) → mark `Not available via MCP`.
- Map rows are tagged **[LIVE]** (verified against a real tenant), **[SCHEMA]** (confirm the JSON path
  on first response), or **[GRAPH]** (`execute_graph_query`/`graph_search`).
- `get_license` scan counts and the `*_grouped` aggregates are **uncapped** — reliable on large
  tenants where service-account `graphSearch` counts were truncating at 10,000.
- This folder is fully standalone: `render_deck.py` + `scripts/` (pure-stdlib render pipeline) +
  `templates/` + `docs/`. There is no service-account or GraphQL code anywhere in it.
