# Token Accuracy Audit — MCP values vs. the deck's true definitions

**Date:** 2026-09-03 · **Scope:** every populated slide 1–6 token on the live tenant
(`<TENANT_ID>`).
**Method:** compare what each MCP source actually *measures* against what the token means in the
original service-account deck (`wiz-health-assessment-skill/scripts/api_delta_processor.py`).

## ❌ CONFIRMED WRONG — fixed to N/A
**Connector family — cloud *accounts* were substituted for *connectors*.**
The dry-run counted `list_subscriptions` (cloud accounts) by status, but the deck's connector tokens
mean connector *deployments* (original: the top-level `connectors` GraphQL field, `api_delta_processor.py:N`).
One connector scans many accounts, so these were off by ~N–N×.

| Token | Was (wrong) | Means | Fix |
|---|---|---|---|
| `CON_TOT` | N | total connectors | **N/A** |
| `CON_EN` | N | connectors w/ status CONNECTED | **N/A** |
| `CON_BRO` | 6 | connectors w/ status ERROR | **N/A** |
| `CON_DIS` | 2 | connectors w/ status DISABLED | **N/A** |
| `CON_K8S` | N | K8s *connector* count (was K8s accounts) | **N/A** |
| `CON_WOS` | N | WizOS/sensor workloads (was a 7%×compute estimate for a different metric) | **N/A** |

Root cause: the Wiz MCP exposes **no connector list** (`get_connector` needs an ID; no `list_connectors`;
connectors aren't Security-Graph entities). Already in the "genuine gap" list: `CON_R`/`CON_VCS`/`CON_NE`/`CON_WE`/`OUT_DEP`/`L_SE`.

## ⚠️ FLAGS — populated but imperfect (your call)
| Token | Value | Issue |
|---|---|---|
| `C_OTH` | N | subtraction (`total − AWS − Azure − GCP`); a direct sum of other-cloud providers earlier gave **N**. Different bases; the direct sum is likely more correct. |
| `WS_T` | N | from `get_license` compute-scan count = **cumulative** scans over the term — same basis problem we fixed for `RCI_T` (corrected N→N). For a consistent coverage denominator it should be the current-entity graph count, not the cumulative license figure. `WS_P` (N%) is computed off it. |
| `DS_B`/`DS_DW`/`DS_PD`/`DS_VD`/`DS_FSS`/`DS_AI` | N / 0 / N / 0 / N / N | from `list_datastores_grouped` = **datastore inventory** counts, but the deck label is "…Scanned." Also `GRAPH_ENTITY_TYPE` grouping may not map data-warehouse/virtual-drive cleanly (both read 0). Inventory ≠ scanned. |
| `F_WMCP` | N | count of `WIZ_MCP` **integrations**; the deck means distinct MCP **users** (close, not identical). |
| `F_PP` | N | `list_controls{created_by:USER}` counts **all** control types (graph+config+risk); the deck means user-created **posture policies** (cloud-config rules) specifically — likely an over-count. |
| `SHI_R_C`/`SHI_R_H` | N / N | **all-time** resolved; deck label says "(Nd)". MCP has no date window → overstates the N-day figure. |
| `CUS_NOD` | N | proxy = days since earliest license start; not the true tenant-creation date. |
| `F_RA`/`F_GA`/`F_BA` | Enabled | original renders "Yes"/"No" — cosmetic format difference only. |

## ✅ VERIFIED CORRECT (spot-checked against original definitions)
- **Big numbers that look scary but are right:** `OC`=N, `OH`≈Nk, `RC`=N, `RH`=N — the original
  deck uses `type:[CLOUD_CONFIGURATION, TOXIC_COMBINATION]` (matches); this tenant simply has tens of
  thousands of issues. `HI_CBC_1`=N is one broad custom rule (a broad custom rule). Not errors.
- AI footprint (`AI_*_COUNT`) — `get_ai_security_summary` totalCounts ✓
- Security posture `SS`/`SP`/`SS_I`/`SG` — `get_security_score` ✓
- Cloud events `CE_*`/`CLOUD_EVENTS_*` — `list_cloud_events_grouped` ✓
- K8s ladder `KC_*`/`KG_*`/`K8S_*`/`K8C_*` — `list_kubernetes_clusters` by deployment status ✓
- Projects `P_HBI/MBI/LBI/TOT`, `U_TOT`=N/`U_ACT`=N/`U_ENG`=N% ✓
- DSPM scans `DS_T/F/SK/P` — status-ratio ✓; **scan-status family** `RCI_*`/`VMI_*`/`NON_*` — graph
  `SECURITY_TOOL_SCAN`, matches the original traversal ✓ (`RCI_T` corrected to graph basis)
- Licenses `L_CO`/`L_DE`/`LU_ADV`/`LU_SENSOR`, contract dates ✓
- VS config, top-control names, cloud registries `R_*/RC_*`, `CLI`=N, `U_RES`=N, `AE_HTTP/NHTTP` ✓
- Adoption `F_AR`/`F_WF`/`F_IR`/`F_TR`/`F_MM`/`F_FW`, agents `F_GA/BA/RA` (functional probes) ✓
- Preview Hub ✓; integrations `IA_*` names + `IR_*` status ✓

## Takeaway
Of the populated slide 1–6 tokens, the **only gross error was the connector family** (now N/A). The
rest are correct, or minor/labeling flags above. Your "grossly off" instinct pinpointed exactly the
one real bug.

---

## 🔁 SUPERSEDED 2026-09-03 — connector family is REACHABLE (`discover` is not the full surface)

**The premise behind the N/A verdict above was wrong.** `discover` is a *curated taxonomy*, not the
full callable surface. `list_deployments` **exists and executes** against the live tenant but is
**not returned by `discover`**. Verified empirically (before/after adding `read_deployments`, and
after an MCP reconnect — the permission grant changed nothing; the tool was always callable). Root
cause per Wiz docs (`docs.wiz.io/docs/wiz-ai-tools`): that page is the **union of Mika-AI + MCP
tools**, some Mika-only / some gated on Wiz AI — so a tool can be documented yet absent from a given
tenant's `discover`. **Rule going forward: to decide "no tool for X", CALL a plausible name and look
for `tool "X" is not available` — never conclude from `discover`'s omission.**

### Connector/deployment tokens — corrected sources (via `list_deployments`)
`list_deployments` accepts `type[]` and `status[]`, ignores `first`, returns N nodes + `totalCount`.
Node `object.__typename:"Connector"` carries `enabled`, `type{id,name}`, `modules[]`.

| Token | Was | Now | Call |
|---|---|---|---|
| `CON_TOT` | N/A | **~sum of 4 types** | `CLOUD`+`KUBERNETES`+`REGISTRY`+`VERSION_CONTROL` connectors |
| `CON_K8S` | N/A | live | `type:["KUBERNETES_CONNECTOR"]` |
| `CON_VCS` | N/A | live | `type:["VERSION_CONTROL_CONNECTOR"]` |
| `CON_R`   | N/A | live | `type:["REGISTRY_CONNECTOR"]` |
| `CON_BRO` | N/A | live | `type:["BROKER"]` (shipped deck defines CON_BRO = brokers, not broken connectors) |
| `CON_ADM` | —   | live | `type:["ADMISSION_CONTROLLER"]` |
| `CON_DIS` | N/A | live | `type:[...],status:["DISABLED"]` |
| `CON_EN`  | N/A | **enable-state only** | `status:["ENABLED"]` — NOT connection-health (see limit below) |
| `OUT_DEP` | N/A | live | `type:["OUTPOST"]` |
| `L_SE`    | N/A | live | `type:["SENSOR"]` (SensorGroups) |

**Hard limit:** `status` enum = `INITIALIZING/DISABLED/ENABLED/UNINSTALLING/UNINSTALLED`. There is
**no `CONNECTED`/`ERROR`** and no health field — the original `CON_EN`=CONNECTED / error-health split
is **not reproducible**; `CON_EN` maps to ENABLED (enable-state), with that caveat noted on the deck.
`CON_WE`/`CON_NE` (connectors with/without cloud events) need per-node `modules[]` inspection across
*all* connectors, but the tool exposes no pagination cursor (N-node cap) — treat as N/A unless paging
is later found.

### Probe sweep (N candidate unlisted names) — one hit
- **VALID (real, unlisted):** `list_automation_rules` — `totalCount:N` (matches portal), exposes
  per-rule `enabled` → can split on/off. This backs `F_AR` (already correct at N).
- **ABSENT (genuine gaps, confirmed by call):** `list_workflows` + all automation-workflow names →
  **`F_WF` (workflows) stays N/A** (automation *rules* ≠ *workflows*); all six workload-scan-log names
  → **workload success/skipped/coverage stays failures-only / N/A**; browser-ext + MCP-usage +
  `list_service_accounts` + `list_connectors`/`list_container_registries`/`get_deployment` → absent.
  So `F_BE`/`F_WMCP` remain audit-log-dedup-or-N/A.
