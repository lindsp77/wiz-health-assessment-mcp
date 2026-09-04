# MCP-Only Coverage — what the Wiz MCP can populate in the existing deck

**Date:** 2026-09-03
**Status:** Authoritative / empirical. Supersedes the desk-level `MCP_COVERAGE_ANALYSIS.md` (2026-09-02).
**Method:** Live probing of the Wiz MCP (`discover` + `execute`) against a real tenant on 2026-09-03,
plus reading the full tool input-schemas for the highest-coverage domains. Read-only.

**Goal of this pass:** Not to change the template. Just to establish, variable-family by
variable-family, what the **Wiz MCP alone** (browser-OAuth, no service account) can realistically
populate in the *current* 440-token deck, and exactly where it falls short — so we can decide how
to structure an MCP-only rebuild.

---

## The one fact that decides everything

`execute_graph_query` and `graph_search` are **Security-Graph only.** `execute_graph_query`
accepts a single `GraphEntityQueryInput` (entity `type` / `select` / `where` / `relationships`
+ fetch flags) — it traverses your **cloud estate** (resources and their relationships). It is
**not** a generic GraphQL passthrough. It cannot issue the top-level GraphQL fields the deck
relies on for platform configuration and analytics:

- `dataScannerSettings`, workload/ASM scanner settings blocks (the slide 17/18 toggles)
- `resourceScanResultsStatusRatio` (uncapped per-status scan ratios)
- `licenses`, `settings`, `endpointExposureLevelSettings`, etc.

So for every metric family there are only three real MCP paths:
1. **A curated domain tool** returns it (best case).
2. **`graph_search`** can traverse the cloud estate for it (works for inventory/estate questions).
3. **Nothing** — the datum lives only behind a top-level GraphQL field → **requires the service account.**

This is why a *pure* MCP build cannot be a 1:1 clone of the current deck.

---

## Coverage by metric family (all 440 tokens roll up into these)

Legend — **FULL**: a curated tool returns essentially the data. **PARTIAL**: topic covered but
shape differs / must be stitched from several tools / some sub-metrics missing. **GRAPH**: only via
`graph_search` estate traversal. **NONE**: no MCP path (service account required). **DERIVED**:
computed by our code from other tokens (inherits its inputs' verdict).

| Slide | Family (tokens) | Best MCP path | Verdict |
|---|---|---|---|
| 3 | AI Footprint — `AI_*_COUNT` (10) | `ai_security.get_ai_security_summary` | **FULL** |
| 3 | Cloud architecture / accounts — `C_AWS/AZ/GCP/OTH`, `CON_TOT`, `CON_K8S/R/VCS` (≈12) | `success.list_subscriptions` (by provider/status) + `list_system_health_issues_grouped_by_deployment` | **PARTIAL** (state split ok; `CON_WE/CON_NE` with/without-events weak) |
| 3 | Sensors / outposts — `CON_WOS`, `L_SE`, `OUT_DEP` (3) | `list_monitored_metrics` (SENSOR_COVERAGE) + deployment grouping | **PARTIAL** |
| 3 | Cloud Events — `CLOUD_EVENTS_1..13`, `CE_1..13` (26) | `soc.list_cloud_events_grouped` | **FULL** |
| 3/4 | Workload inventory — `K8S`, `R_TOT`, `SERVERLESS_*`, `TI`, `U_RES` (≈7) | `inventory` grouped resource counts + `graph_search` | **FULL/PARTIAL** |
| 4 | Workload scans — `WS_T/P/F/SK` (4) | **`success.get_license` (`include_compute_scan_count`)** — uncapped; per-status split needs graph | **PARTIAL→FULL** |
| 4 | CI/CD scans — `CLI` (1) | `codesec`/`inventory` CI-CD scan tools | **PARTIAL** |
| 4 | Red Agent — `RA_DAST/WC/SI/TOTS` (4) | `attack_surface` (Red Agent findings/scans) | **PARTIAL/FULL** |
| 4 | Contract / renewal — `CONTRACT_END_FMT`, `CUS_NOD`, `D_U_R` (3) | `success.list_licenses` (expiration dates) | **PARTIAL** |
| 4 | Cloud Advanced — `CL_*` (8) | DERIVED from scan/coverage tokens | **DERIVED** |
| 5 | Container-image scans — `RCI_T/F/S/C` (4) | `get_license` (`include_registry_container_image_scan_count`, uncapped) + graph for status split | **PARTIAL** |
| 5 | VM-image scans — `VMI_T/F/S/C` (4) | `graph_search` SECURITY_TOOL_SCAN by status | **GRAPH/PARTIAL** |
| 5 | Non-OS disk scans — `NON_T/F/S/C` (4) | `graph_search` SECURITY_TOOL_SCAN (workload type) by status | **GRAPH/PARTIAL** |
| 5 | DSPM scans — `DS_T/F/SK/P` (4) | `dspm.get_data_scan_results` | **FULL** |
| 5 | DSPM breakdown — `DS_B/DW/PD/VD/FSS/AI` (6) | `dspm.list_datastores_grouped` | **FULL** |
| 5 | System Health — `SHI_C/H`, `SHI_R_C/H`, `SHI_B/CC/I/KC/O/RC/VCS` (11) | `success.list_system_health_issues` + `..._grouped_by_deployment` | **FULL** (resolved-in-30d window is PARTIAL) |
| 6 | Adoption & governance — `F_*` (14) | mixed: `automation` (`F_AR/F_WF`), `success` frameworks/metrics (`F_FW/F_MM/F_BE`) | **PARTIAL** (agent toggles `F_BA/GA/RA`, tag/discovery rules `F_TR/F_DR`, `F_WMCP` weak/missing) |
| 6 | Integrations activity — `IA_1..10`, `IR_1..10` (20) | `success.list_integrations` (name/type/status) | **PARTIAL** (last-activity dates not exposed) |
| 6/15 | Kubernetes ladder — `KC_*`, `KG_*`, `K8S_1..5`, `K8C_*` (≈25) | `success.list_kubernetes_clusters` (per-cluster connector/admission/sensor/auditlog/internet status) | **FULL** (counts need client-side aggregation; 30/page) |
| 6 | Projects / users — `P_*`, `U_*`, `PC_*`, `CC_TOT` (≈10) | `success.list_projects` (HBI/MBI/LBI) + `get_platform_adoption_metrics` + champion-center | **FULL** |
| 7/8 | Preview Hub — billable/non-billable, public/private tiers (7) | `success.list_preview_migration_hub_items` (filters by enabled/type/license tier) | **FULL** |
| 9 | Roadmap tracker — `ROADMAP_TRACKER` (1) | `docs`/`success` product-updates & roadmap | **PARTIAL** (customer-tracked items with ticket/status/quarter may not be exposed) |
| 11 | Top controls — `CI_CONTROL_*`, `HI_CONTROL_*` + counts (12) | `issues.list_issues_grouped` (by source rule / severity) | **FULL** |
| 11 | ASM estimated workloads — `AE_TOT` (1) | DERIVED from endpoints | **DERIVED** |
| 12 | AI findings — `AI_SF/IF/MF` (3) | `ai_security.list_ai_security_findings` | **FULL/PARTIAL** |
| 12 | Security posture — `SS/SP/SS_I/SG/s1d/OC/OH/RC/RH/RJ` (10) | `success.get_security_score` (score + industry & workload benchmark + name) + `issues` counts | **FULL** |
| 12 | Issue age / MTTR — `AVG_AGEC/AGEH`, `MTTR_O` (3) | `issues` (may need client-side computation) | **PARTIAL** |
| 12 | Threats — `OT`, `RT` (2) | `soc.list_threats` / detections | **FULL/PARTIAL** |
| 13 | App endpoints — `AE_HTTP/NHTTP` (2) | `attack_surface` endpoints / `list_monitored_metrics` (APPLICATION_ENDPOINT_COUNT) | **FULL/PARTIAL** |
| 14 | Licenses — `L_CO`, `L_DE`, `L_CL_PCT` (3) | `success.list_licenses` (SKU/status); `L_CL_PCT` DERIVED | **FULL** |
| 15 | Container registries — `R_1..6`, `RC_1..6`, `R_AUT/CON/CUS` (≈15) | `inventory` grouped registry counts | **PARTIAL** (scanning-method split weak) |
| 15 | Container image lifecycle — `CL_CODE/BLD/STR/DEP/CLD/RT` (6) | `graph_search` by lifecycle stage | **GRAPH/PARTIAL** |
| **17** | **ASM scanner config — `ASM_*` (18 + 18 `_R`)** | `attack_surface.list_attack_surface_rules` = rule *catalog*, not the settings block | **PARTIAL/NONE** (~2–4 inferable) |
| **17** | **Workload scanner config — `WS_*` (14 + 14 `_R`)** | `get_non_os_disk_scanning_settings` + a few | **PARTIAL** (~2–3 of 14) |
| **18** | **Data scanner config — `DSS_*` (19 + 19 `_R`)** | none exists (checked dspm/settings/general/vulnerabilities) | **NONE** (0 of 19) |
| **18** | **Vuln scanner config — `VS_*` (13 + 13 `_R`)** | `vulnerabilities.get_vulnerability_assessment_settings` | **FULL** (~13 of 13 — *refutes* old desk-guess) |
| 19 | Potential integrations — `PI_T{1,2,3}_*` (72) | `graph_search` TECHNOLOGY → SERVICE_ACCOUNT traversal | **GRAPH** (doable) |

---

## The crux: scanner-config slides 17 & 18

These are the "✓ aligned / ✗ revisit" toggle slides — a signature part of the deck. Of the
**64 config value-tokens** (plus an equal number of derived `_R` recommendation tokens):

| Block | Value tokens | MCP-reachable | Verdict |
|---|---|---|---|
| Vulnerability scanner (`VS_*`) | 13 | ~13 | **FULL** ✅ |
| Workload scanner (`WS_*`) | 14 | ~2–3 | **PARTIAL** |
| ASM scanner (`ASM_*`) | 18 | ~2–4 | **PARTIAL/NONE** |
| Data scanner (`DSS_*`) | 19 | 0 | **NONE** ❌ |

→ **~17–20 of 64 reachable; ~44–47 are not.** With the `_R` tokens, roughly **~90 tokens (~20%
of the whole deck)** cannot be produced by MCP alone. **Slides 17 & 18 cannot be built from the
MCP alone as designed.** `dataScannerSettings` (all of slide-18 DSS) has no MCP surface at all,
and the ASM scanner-settings block (mode / advanced scan sources / risk & exposure toggles) is
not exposed — `list_attack_surface_rules` returns the 900+ detection-rule catalog, a different thing.

---

## Headline tally (of 440 tokens)

- **~230–250 FULL or DERIVED-from-FULL** — curated tools return them cleanly (AI, cloud events,
  DSPM, system health, K8s, projects/users, preview hub, top controls, posture/score, licenses,
  VS config).
- **~90 PARTIAL** — right topic, wrong shape or must be stitched (adoption toggles, integrations
  activity dates, registries method split, contract dates, scan per-status splits, MTTR/age).
- **~72 GRAPH** — Potential Integrations traversal (works via `graph_search`).
- **~90 NONE** — the DSS block + most WS/ASM config toggles (slides 17/18) → **service account only.**

Net: an MCP-only build can populate on the order of **~70–75%** of the deck well, another chunk
partially, and structurally loses ~20% (the config-toggle slides).

---

## What this means for the rebuild (decision needed)

A **pure**-MCP version (the goal, for internal Wiz approval) is achievable **only if we accept
degrading slides 17 & 18.** The options considered:

- **Option 1 — Drop/trim the config slides.** Keep VS config (FULL) + whatever WS/ASM toggles MCP
  exposes; remove the DSS block and the unreachable WS/ASM toggles. Cleanest "MCP-only" story;
  loses deck fidelity on a signature section.
- **Option 2 — Render config slides as "not assessed via MCP" ✅ CHOSEN (2026-09-03).**
  Keep the slide 17/18 layouts, populate every toggle MCP can reach (all of VS, the 2–3 WS and
  2–4 ASM toggles that are exposed), and mark the remainder — the whole DSS block and the
  unreachable WS/ASM toggles — with an explicit **"Not assessed via MCP"** placeholder rather than
  a blank or a misleading ✗. Honest and preserves the layout.
- **Option 3 — Hybrid (defeats "MCP-only").** MCP for ~80%, a thin service-account call just for
  the config blocks. Best fidelity, but not the approval story Wiz wants.

The rest of the deck (slides 3–15, 19) is well within reach, and MCP actually *fixes* the
large-tenant pain: `get_license` scan counts and the `*_grouped` aggregate tools sidestep the
10,000-row Security-Graph cap that was silently truncating big accounts.

### Build plan (given Option 2)

1. **MCP data-collector** — a new collector that calls the curated tools / `graph_search`
   traversals mapped above and emits the same token dictionary the template consumer already
   expects (so the PPTX/CSV pipeline is unchanged). Fill the FULL + GRAPH set first.
2. **Config-toggle handling** — populate the MCP-reachable toggles (VS full; the exposed WS/ASM
   ones); emit a sentinel (e.g. `"Not assessed via MCP"`) for the DSS block + unreachable WS/ASM
   toggles, and make the ✓/✗ recommendation renderer treat the sentinel as N/A (no green/red).
3. **Auth** — browser-OAuth via the Wiz MCP; no service account, no `.env` secrets.
4. **Parity check** — run MCP-only vs the existing service-account run on the same tenant and diff
   the token dictionaries to quantify real coverage and catch shape mismatches.
