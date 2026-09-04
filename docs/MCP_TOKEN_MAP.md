# MCP Token Map — every deck token → its Wiz MCP source (or "Not available via MCP")

**Date:** 2026-09-03  ·  **Mode:** MCP-only (browser-OAuth, no service account, no data-collection script).
**Companion to:** `skills/wiz-health-assessment-mcp/SKILL.md` (the runbook that executes this map).
**Grounding:** rows marked **[LIVE]** were verified against a real tenant on 2026-09-03; **[SCHEMA]**
are mapped from the tool's input/output schema — confirm the exact JSON path at runtime;
**[GRAPH]** need `graph_search` (Security-Graph traversal).

> Every call is `mcp__claude_ai_Wiz_MCP__execute(tool_name=<tool>, parameters={...})`.
> All are read-only. Counts come from a filtered call's `totalCount` or an aggregate count field —
> you do NOT need to page all rows. Where a token is not reachable, write the literal
> **`Not available via MCP`** (the CSV/`_R` treatment renders it as N/A).

---

## ✅ Verified runtime corrections (from the 2026-09-03 validation run)

These override the per-call tables below where they differ. They were found by actually running
every call against a live tenant — apply them and the run works first-try (no retries).

1. **`list_kubernetes_clusters` status filters need their `*_property_name` companion.** Passing
   `connector_status_contains_any:["Installed"]` alone throws `internal unexpected error`. Always add
   the property name, e.g. `{connector_status_contains_any:["Installed"], connector_status_property_name:"deploymentCoverage_connector_deploymentStatus", first:1}`.
   Same for `admission_controller_status` (`deploymentCoverage_admissionController_deploymentStatus`),
   `sensor_status` (`deploymentCoverage_sensor_deploymentStatus`),
   `audit_log_collector_status` (`deploymentCoverage_auditLogCollector_deploymentStatus`),
   `kubernetes_flavor` (`kubernetes_kubernetesFlavor`), `accessible_from_internet` (`accessibleFrom.internet`).
2. **`list_endpoint_attack_surfaces` and `list_attack_surface_findings` use `limit`, not `first`.**
   (`list_threats` correctly uses `first`.)
3. **`get_data_scan_results`** is a `graph_search` wrapper; status enum is
   `ScanStatusSuccess` / `ScanStatusError` / `ScanStatusSkipped` (not SUCCESS/FAILED/SKIPPED). The
   unfiltered `totalCount` can slightly exceed the three status buckets (a Processing/NA sliver) —
   use the unfiltered total for `DS_T`.
4. **`list_datastores_grouped`** takes `group_by` as a **plain string** from a fixed enum
   (`CLOUD_ACCOUNT|PROJECT|GRAPH_ENTITY_TYPE|CLOUD_PLATFORM`). Use `group_by:"GRAPH_ENTITY_TYPE"` →
   per-type `resourceCount` (BUCKET, DATABASE, DB_SERVER, FILE_SYSTEM_SERVICE, SNAPSHOT, AI_DATASET).
   A type absent from the response = 0 (e.g. no VIRTUAL_DRIVE ⇒ `DS_VD=0`).
5. **`list_cloud_resources_grouped`**: pattern is `{type_equals:["X"], group_by:["TYPE"]}` → one
   aggregate node with `analytics.resources.count`. For the registry-type ladder (`R_1..6`/`RC_1..6`)
   group by **`NATIVE_TYPE`**, not the type name.
6. **`list_cloud_events_grouped`** requires `{group_by_fields:["origin"], include_count:true}`;
   default page size caps at N.
7. **`list_issues_grouped` with `group_by:"SOURCE_RULE"` returns only the rule `id`, no name.**
   Resolve names via `list_controls{search:"<rule-id>"}` (exact-ID search). Do NOT resolve via
   `list_issues{source_rule_id:...}` (can return a co-attached rule on multi-rule toxic combinations).
8. **Container-image lifecycle (`CL_BLD/CLD/CODE/DEP/RT/STR`) is NOT reachable.**
   `list_cloud_resources_grouped{group_by:["LIFECYCLE_STAGE"]}` returns opaque base64 group IDs with
   `name:null` — no way to label them via MCP. → **`Not available via MCP`.**
9. **`WS_NONOS` / `WS_EXCL`** come from **`get_non_os_disk_scanning_settings`** (in the
   `vulnerabilities` domain), NOT `get_vulnerability_assessment_settings`.
10. **`filter_scope` lives ONLY on `list_issues`, NOT on `list_issues_grouped`.** `list_issues` accepts
    `filter_scope:["ALL_ISSUE_DETECTIONS"|"LATEST_ISSUE_DETECTION"]` (default ALL). `list_issues_grouped`
    has **no such param** — passing it errors (`additionalProperties 'filter_scope' not allowed`), so the
    grouped top-control counts (`HI_CBC_*`/`CI_CBC_*`) are ALWAYS `ALL_ISSUE_DETECTIONS` and cannot be scoped.
    ⚠️ **Live-validated 2026-09-04: on this tenant `ALL == LATEST`** — identical totals for both the
    tenant-wide open-HIGH count and the top rule under either scope. So `OC`/`OH` are **not** scope-inflated,
    and a large `HI_CBC_1` is a **real** count, not an artifact: here a single broad custom toxic-combination
    rule accounts for ~89% of all open HIGH. **Do NOT report `HI_CBC_1` as "inflated by scope."** (An earlier
    note claimed LATEST vs ALL diverges; that was not reproducible on 2026-09-04 — treat scope divergence as
    tenant/version-specific, not assumed.) **If a future tenant does diverge:** rank rule IDs via
    `list_issues_grouped{group_by:"SOURCE_RULE"}`, then re-count each with
    `list_issues{source_rule_id:[id], severity, status, filter_scope:"LATEST_ISSUE_DETECTION"}.totalCount`
    (only `list_issues` carries the scope) — that yields per-rule LATEST counts comparable to `OC`/`OH`.
11. **`C_OTH`**: prefer the **direct** filtered call (sum of non-AWS/Azure/GCP providers) over the
    subtraction formula — the two disagreed (N vs N) because `CON_EN`/total counts connectors
    differently than provider sums. Compute `C_OTH` and `C_OTH_NAMES` from explicit provider filters.
12. **`SERVERLESS` split** — `type_equals:["SERVERLESS"]` = serverless *functions* → `SERVERLESS_FN_COUNT`.
    Serverless *containers* come from a separate type: `type_equals:["CONTAINER_SERVICE"], group_by:["TYPE"]`
    → `nodes[0].analytics.resources.count` → `SERVERLESS_CT_COUNT` (validated 2026-09-03 = N).
13. **`list_system_health_issues` `deployment_type` has no `BROKER` value** — for `SHI_B`/`SHI_O`/`SHI_I`
    use `list_system_health_issues_grouped_by_type` / `_grouped_by_deployment` instead.
14. **AI inventory counts — ALL from `get_ai_security_summary` LIFETIME totals (validated 2026-09-04).**
    The AI-Security console shows lifetime counts; the deck's "AI Visibility / Inventory" must match it.
    Use `get_ai_security_summary{}` totalCounts for EVERY AI_*_COUNT — do NOT use `list_cloud_resources`
    active-inventory (that undercounts): `AI_AGENTS_COUNT`=aiAgents(N), `AI_MODELS_COUNT`=aiModels(N),
    `AI_GUARDRAILS_COUNT`=aiGuardrails(N), `AI_PIPELINES_COUNT`=aiPipelines(N),
    `AI_MCP_SERVERS_COUNT`=mcpServers(N), `AI_TECHNOLOGIES_COUNT`=aiTechnologies(N),
    `AI_WORKLOADS_COUNT`=aiWorkloadsTotal(N), `AI_CA_COUNT`=codingAgents(N),
    `AI_CODE_REPOS_COUNT`=codeRepoWithAi(N). `AI_DATASETS_COUNT`=**N** (no aiDatasets field in the
    summary → `list_cloud_resources{type_equals:["AI_DATASET"]}` all-status totalCount; console shows N).
15. **Workload counts come from the LICENSE page, not graph/deployment tools** (validated 2026-09-03).
    `get_license{license_id:<core license>, start_at, end_at, include_compute_scan_count:true}` →
    `billableWorkloadTrendV2.averageServerlessContainerCount` (`SERVERLESS_CT_COUNT`=N, exact) and
    `.averageContainerHostCount` (~N-227). These `average*` fields are **window-sensitive** (accumulated
    ÷ span incl. zero days) — a recent ~N-day window reproduces the portal; the full license term
    collapses them toward 0. **`CH_TOT` (Container Hosts, slide 3)** = `averageContainerHostCount` (N) —
    this token was added (slide-3 box relabeled R_TOT→CH_TOT).
17. **`R_TOT` (Container Registries) = `list_cloud_resources_grouped{type_equals:["CONTAINER_REPOSITORY"], group_by:["CLOUD_ACCOUNT","REGION"]}` totalCount** (validated 2026-09-03: N active / N incl. deleted; portal N). Counts *populated* registries — distinct (account,region) pairs holding ≥1 repository. Do NOT use `type_equals:["CONTAINER_REGISTRY"]` (=N: AWS ECR auto-provisions an empty registry per region per account) nor `list_container_images_grouped{CONTAINER_REGISTRY}` (=N).
18. **Data-scan counts (`DS_T`/`DS_F`/`DS_SK`/`DS_P`) — use `execute_graph_query` on `SECURITY_TOOL_SCAN`, NOT `get_data_scan_results`.** See `docs/wiz-scan-counts.md`. `get_data_scan_results` returns a subset with workload rows mixed in (N vs the true N). Correct (validated 2026-09-03, reconciled): `DS_T`=N, `DS_SK`=N, `DS_F`=`ScanStatusError`=N (⚠️ `ScanStatusFailed` returns 0 silently — does not exist), `DS_P`=success/total=N/N=N%. Reconcile N+N+N=N before reporting.
16. **`L_SE` (runtime sensor UNIT count, e.g. N) is NOT exposed by any MCP tool** — `get_license`'s
    `billableWorkloadTrendV2` (N fields) has no sensor field; `list_deployments{type:["SENSOR"]}`=N
    counts sensor *groups* not units; `wm-sensor-coverage` is a %; sys-health-by-deployment is a
    with-issues floor. → `Not available via MCP` (was wrongly N). Licensing concept, flag to TAM.
19. **Posture-snapshot AI findings + Open Threats (validated 2026-09-04):**
    - `AI_SF` (AI Security Findings) = **`list_ai_security_findings{}` totalCount** (=N). CLEAN. Do NOT
      use get_ai_security_summary criticalIssues+highIssues (=N, wrong).
    - `AI_MF` ("Configuration Findings") = **sum of `analytics.failCount` across the AI-Security-tagged
      Cloud Config Rules**: `list_cloud_configuration_rules{framework_category:["wct-id-1998"]}` (N rules) →
      Σ failCount = N. (`list_issues{security_risk:["wct-id-1998"]}`=N catches only toxic-combos, misses
      standalone config findings.) ⚠️ Derived sum — verify definition holds on other tenants.
    - `AI_IF` (AI Inventory Findings) = `list_inventory_findings{resource_type:["AI_MODEL","MCP_SERVER"]}`
      (=N: N+N). ⚠️ Console scopes to Models+MCP only (full AI taxonomy=N); empirically matched the reference tenant's N — confirm the console's scope before trusting on other tenants.
    - `OT` (Open Threats) = `list_threats{status:["OPEN"]}` MINUS MEDIUM+INFORMATIONAL severities
      (=N: N total − N MED − N INFO). Use `severity:["CRITICAL","HIGH","LOW"]` filter. ⚠️ Empirically
      matched — console excludes MED+INFO from the "Open Threats" widget.

---

## Available via MCP — by call

### 1. `get_security_score` {metric_id:"wm-security-score"} · success · [LIVE]
| Token | Source path |
|---|---|
| `SS` | `monitoredMetric.lastSuccessfulRun.results.score` |
| `SP` | `monitoredMetricsBenchmarks.securityScore.<band>.percentile50` — `<band>` per `monitoredMetricSettings.defaultBenchmarkComparisonMode` (`INDUSTRY_AND_WORKLOAD_COUNT`→`byIndustryAndWorkloadCount`, `INDUSTRY`→`byIndustry`, `WORKLOAD_COUNT`→`byWorkloadCount`) |
| `SS_I` | `viewerV2.tenant.industry` (title-case, e.g. `SOFTWARE_B2B`→"Software B2B") |
| `SG` | derived: `SP - SS` |

### 2. `get_ai_security_summary` {} · ai_security · [LIVE]
| Token | Source path |
|---|---|
| `AI_AGENTS_COUNT` | `aiAgents.totalCount` |
| `AI_GUARDRAILS_COUNT` | `aiGuardrails.totalCount` |
| `AI_MODELS_COUNT` | `aiModels.totalCount` |
| `AI_PIPELINES_COUNT` | `aiPipelines.totalCount` |
| `AI_TECHNOLOGIES_COUNT` | `aiTechnologies.totalCount` |
| `AI_WORKLOADS_COUNT` | `aiWorkloadsTotal.totalCount` |
| `AI_MCP_SERVERS_COUNT` | `mcpServers.totalCount` |
| `AI_CA_COUNT` | `codingAgents.totalCount` |
| `AI_CODE_REPOS_COUNT` | `codeRepoWithAi.totalCount` |
| `AI_SF` | `criticalIssues.totalCount` + `highIssues.totalCount` (AI findings) |

### 3. `get_platform_adoption_metrics` {} · success · [LIVE]
| Token | Source path |
|---|---|
| `U_ACT` | `activeUsers.lastSuccessfulRun.results.count` |
| `P_TOT` | `projects.totalCount` |

### 4. `list_projects` {first:1, root_projects_only:false} · success · [LIVE]
| Token | Source path |
|---|---|
| `P_HBI` | `projects.HBICount` |
| `P_MBI` | `projects.MBICount` |
| `P_LBI` | `projects.LBICount` |
| `P_TOT` | `projects.totalCount` |
| `PC_TOT` | derived: `totalCount` − (root count from a second call with `root_projects_only:true`) |

### 5. `list_licenses` {} · success · [LIVE]
Reads `viewerV2.tenant.licenses[]` (each: `name`, `sku`, `status`, `startAt`, `endAt`, `isTrial`).
| Token | Rule |
|---|---|
| `L_CO` | "Active" if any `status==ACTIVE` license `sku` is a Code SKU (`CODE`/`WIZ_CODE`), else "Inactive" |
| `L_DE` | "Active" if any `status==ACTIVE` license `sku` is a Defend SKU (`DEFEND`), else "Inactive" |
| `CONTRACT_END_FMT` | max `endAt` among ACTIVE core licenses (`ONE`/platform), MM/DD/YYYY |
| `D_U_R` | derived: days from today → `CONTRACT_END` |

### 6. `list_subscriptions` (one call per filter, read `.cloudAccounts.totalCount`) · success · [LIVE]
| Token | Params |
|---|---|
| `C_AWS` | `{cloud_provider:["AWS"], first:1}` |
| `C_AZ` | `{cloud_provider:["Azure"], first:1}` |
| `C_GCP` | `{cloud_provider:["GCP"], first:1}` |
| `C_OTH` | total − (AWS+AZ+GCP) |
| `CON_TOT`/`CON_EN`/`CON_DIS`/`CON_BRO` | **CLOUD connectors ONLY (validated 2026-09-04 — NOT all 4 types).** `CON_TOT`=`list_deployments{type:["CLOUD_CONNECTOR"]}` totalCount (=N); `CON_EN`=`+status:["ENABLED"]` (=N); `CON_DIS`=`+status:["DISABLED"]` (=5); `CON_BRO`=BROKER count=`list_deployments{type:["BROKER"]}` totalCount (=N) — the slide-3 box is labeled **"Broker Deployments"** (shipped deck reused CON_BRO for brokers despite the misleading "Connectors-Errored" CSV title). (Errored cloud connectors ~N via list_system_health_issues category:[ERROR] is a SEPARATE metric with no deck slot.) `CON_K8S`/`CON_R`/`CON_VCS` are SEPARATE per-type totals, not part of CON_TOT. |
| `C_AWS`/`C_AZ`/`C_GCP`/`C_OTH` | **Cloud CONNECTORS by provider, NOT accounts** (validated 2026-09-04). `list_deployments` accepts a `cloud_provider` array param (unlisted): `{type:["CLOUD_CONNECTOR"], cloud_provider:["AWS"]}` totalCount = **C_AWS**(N); Azure=N, GCP=N; `C_OTH`=N−(AWS+AZ+GCP)=N. Do NOT use `list_subscriptions` (that counts cloud ACCOUNTS → wrong, was N/N/N). |

### 7. `list_kubernetes_clusters` (one call per filter, read `.cloudResourcesV2.totalCount`) · success · [LIVE]
| Token | Params |
|---|---|
| `K8C_TOT`, `K8S` | `{first:1}` |
| `KC_WC` | `{connector_status_contains_any:["Installed"], first:1}` |
| `KG_NC` | `{connector_status_contains_any:["NotInstalled"], first:1}` |
| `KC_AC` | `{admission_controller_status_contains_any:["Installed"], first:1}` |
| `KC_CLI` | `{sensor_status_contains_any:["Installed"], first:1}` |
| `KG_NS` | `{sensor_status_contains_any:["NotInstalled"], first:1}` |
| `KC_SE` | `{audit_log_collector_status_contains_any:["Installed"], first:1}` |
| `KG_NA` | `{audit_log_collector_status_contains_any:["NotInstalled"], first:1}` |
| `KG_IA` | `{accessible_from_internet_equals:true, first:1}` |
| `K8S_1..5` / `K8C_1..5` | one call per `kubernetes_flavor_contains_any:["EKS"|"AKS"|"GKE"|"OpenShift"|...]`, take name+totalCount, rank top 5 |
| `K8C_OTH` | `K8C_TOT` − sum(top 5) |

### 8. `list_system_health_issues` (read severity counts) · success · [LIVE]
| Token | Params → field |
|---|---|
| `SHI_C` | `{severity:["CRITICAL"],status:["OPEN"],first:1}` → `systemHealthIssues.criticalSeverityCount` |
| `SHI_H` | `{severity:["HIGH"],status:["OPEN"],first:1}` → `highSeverityCount` |
| `SHI_CC` | `{deployment_type:["CLOUD_CONNECTOR"],severity:["CRITICAL","HIGH"],status:["OPEN"]}` → crit+high |
| `SHI_KC` | `deployment_type:["KUBERNETES_CONNECTOR"]` |
| `SHI_RC` | `deployment_type:["REGISTRY_CONNECTOR"]` |
| `SHI_VCS` | `deployment_type:["VERSION_CONTROL_CONNECTOR"]` |
| `SHI_O` | `deployment_type:["OUTPOST"]` (+ OUTPOST_CLUSTER) |
| `SHI_B` | `deployment_type:["BROKER"]` |
| `SHI_I` | `deployment_type:["INTEGRATION"]` (+ SERVICE_ACCOUNT) |

### 9. `list_issues_grouped` {group_by:"SOURCE_RULE", type:["CLOUD_CONFIGURATION","TOXIC_COMBINATION"], fetchIssues:false, fetchSecurityScoreImpact:false, first:3} · issues · [LIVE-schema]
Call once with `severity:["CRITICAL"]`, once with `severity:["HIGH"]`. Nodes ranked by count.
Counts are always `ALL_ISSUE_DETECTIONS` (this tool has no `filter_scope` — see correction #10); a very
large `HI_CBC_1` is usually one broad custom rule, NOT a scope inflation — report it as-is.
Resolve each node's rule name via `list_controls{search:"<rule id>"}` (grouped returns only `id`, see #7).
| Token | Source |
|---|---|
| `CI_CONTROL_1..3` | crit call `nodes[0..2].name` |
| `CI_CBC_1..3` | crit call `nodes[0..2]` issue count |
| `HI_CONTROL_1..3` | high call `nodes[0..2].name` |
| `HI_CBC_1..3` | high call `nodes[0..2]` issue count |

### 10. `list_issues` (read `.totalCount`) · issues · [LIVE-schema]
| Token | Params |
|---|---|
| `OC` | `{severity:["CRITICAL"],status:["OPEN"]}` |
| `OH` | `{severity:["HIGH"],status:["OPEN"]}` |
| `RC` | `{severity:["CRITICAL"],status:["RESOLVED"],resolved_at_after:<today-90d>}` |
| `RH` | `{severity:["HIGH"],status:["RESOLVED"],resolved_at_after:<today-90d>}` |
| `RJ` | `{status:["REJECTED"]}` |

### 11. `list_endpoint_attack_surfaces` (read `.totalCount`) · issues · [LIVE-schema]
| Token | Params |
|---|---|
| `AE_HTTP` | `{protocol:["HTTP","HTTPS"], is_third_party_application:false}` |
| `AE_NHTTP` | `{protocol:["SSH","RDP","WIN_RM","OTHER"], is_third_party_application:false}` |
| `AE_TOT` | derived: `round(AE_HTTP/25 + AE_NHTTP/50)` (25 / 50 are fixed scaling divisors, not tenant values) |
| `RA_WC` | `{scan_source:["RECON"]}` (AI web-crawler endpoints) |

### 12. `list_attack_surface_findings` (read `.totalCount`) · issues · [LIVE-schema]
| Token | Params |
|---|---|
| `RA_DAST` | `{is_ai_powered:true, finding_type:["EXPLOITABILITY_VALIDATION"], status:["OPEN"]}` |
| `RA_SI` | `{is_ai_powered:true, finding_type:["DEFAULT_CREDENTIALS"]}` (secret-impact proxy — confirm) |

### 13. `get_vulnerability_assessment_settings` {} · vulnerabilities · [LIVE] (config slide 18, FULL)
| Token | Source path |
|---|---|
| `VS_ARTIF` | `vulnerabilityAssessmentSettings.codeLibraries.artifactsLifecycleStages` |
| `VS_LOCK` | `codeLibraries.lockFilesLifecycleStages` |
| `VS_MANIF` | `codeLibraries.manifestFilesLifecycleStages` |
| `VS_GRADL` | `codeLibraries.gradleScopes` |
| `VS_MAVEN` | `codeLibraries.mavenScopes` |
| `VS_JSDEP` | `codeLibraries.npmScopes` / `npmInstalledJavascriptLibrariesVulnerabilitiesEnabled` |
| `VS_EOL` | `endOfLifeTechnologies.upcomingDetectionEnabled` (+ `upcomingDetectionDays`) |
| `VS_GOSTD` | `goStandardLibraryVulnerabilitiesEnabled` |
| `VS_RHOS` | `ignoreRedHatOpenshiftContainerLibraryVulnerabilities` |
| `VS_EXCL` | `legacyCodeLibraryExclusionPathsEnabled` |
| `VS_OSPKG` | `osPackageManagedCodeLibrariesVulnerabilitiesDetectionEnabled` |
| `VS_WINB` | `windowsManagedVulnerabilitiesDetectionEnabled` |

### 14. `list_cloud_events_grouped` {} · soc · [SCHEMA]
| Token | Source |
|---|---|
| `CLOUD_EVENTS_1..N` | top-13 group display names by volume |
| `CE_1..N` | matching group counts |

### 15. `list_threats` {status:["OPEN"]} · soc · [SCHEMA]
| Token | Source |
|---|---|
| `OT` | open threat detections `totalCount` |

### 16. Data-scan counts via `execute_graph_query` on `SECURITY_TOOL_SCAN` · [LIVE] — see `docs/wiz-scan-counts.md`
⚠️ **Do NOT use `get_data_scan_results`** (subset + workload rows mixed; gave N vs true N).
| Token | Source |
|---|---|
| `DS_T`/`DS_F`/`DS_SK`/`DS_P` | `execute_graph_query{query:{type:["SECURITY_TOOL_SCAN"], select:true, where:{dataSource_name:{EQUALS:["Wiz Data Scanner"]}, status:{EQUALS:[...]}}}, first:1}` → `graphSearch.totalCount` (check `maxCountReached`). `DS_T`=no status filter=N; `DS_SK`=`ScanStatusSkipped`=N; `DS_F`=`ScanStatusError`=N; `DS_P`=Success(N)/`DS_T`=N%. **Reconcile Success+Skipped+Error=Total.** [LIVE 2026-09-03] |
| `DS_P` | derived per original formula = `(DS_T − DS_F − DS_SK) ÷ DS_T` (= coverage/scan-success ratio); `CL_DP`=`DS_P` |
| `DS_B`/`DS_PD`/`DS_VD`/`DS_AI`/`DS_DW`/`DS_FSS` | **RECOVERED 2026-09-03** — partition the data-scan query by `scannedResourceType` (add to the `where` alongside `dataSource_name:["Wiz Data Scanner"]`). `DS_B`=`Bucket`=N; `DS_PD`=`Database`=N (managed/PaaS; `DBServer`=N is hosted-on-VM, separate); `DS_VD`=`NonOSDisk`=N (data disks/volumes); `DS_AI`=`AiDataset`=6; `DS_DW`=0 and `DS_FSS`=0 (data scanner has NO DataWarehouse / FileSystem `scannedResourceType` — those are not scanned as distinct types). Reconciliation of the full data-scanner set: Bucket N + Serverless N + OSDisk N + VMImage N + ContainerImage N + Database N + DBServer N + NonOSDisk N + AiDataset 6 + **RepositoryBranch N** = N, + ~N rare/other = N. ⚠️ `RepositoryBranch` (code-repo data scans) is a real `scannedResourceType` NOT in the standard 9-value enum — found by sampling per `wiz-scan-counts.md`. |

### 17. `get_license` {license_id, start_at, end_at, include_compute_scan_count:true, include_registry_container_image_scan_count:true} · success · [SCHEMA]
Uncapped scan counts — bypasses the Nk Security-Graph cap (fixes large-tenant truncation).
| Token | Source |
|---|---|
| `WS_T` | compute scan count (VM disk + serverless + container image + container host) |
| `RCI_T` | registry container image scan count |

### 18. `list_cloud_resources_grouped` {group_by:...} · inventory / ai_security · [SCHEMA]
| Token | group_by |
|---|---|
| `TI` | CONTAINER_IMAGE total |
| `R_TOT`, `R_1..6`/`RC_1..6` | CONTAINER_REGISTRY by registry type |
| `SERVERLESS_FN_COUNT` | SERVERLESS |
| `AI_DATASETS_COUNT` | AI_DATASET |

### 19. `list_preview_migration_hub_items` {enabled:true, license_categories:[...]} · success · [SCHEMA]
| Token | Filter |
|---|---|
| `BILLABLE_ADVANCED` | enabled features, `license_categories:["ADVANCED"]`, billable |
| `BILLABLE_CODE` | `["CODE"]` | 
| `BILLABLE_DEFEND` | `["DEFEND"]` |
| `BILLABLE_SENSOR` | `["SENSOR"]` |
| `ALL_NON_BILLABLE_PREVIEW`, `PRIVATE_BILLABLE`, `PRIVATE_NON_BILLABLE` | by feature_type / billable split |

### 20. `list_monitored_metrics` {builtin:false} + `list_compliance_frameworks` {created_by:"USER", enabled:true} · success · [SCHEMA]
| Token | Source |
|---|---|
| `F_MM` | count of custom (builtin:false) monitored metrics |
| `F_BE` | **N/A** — deck wants distinct browser-ext *users*; the `BROWSER_EXTENSION_ACTIVE_USER_COUNT` metric is empty/unreliable and the audit-log performer path needs `admin:audit`. Mark `Not available via MCP`. |
| `F_FW` | `list_compliance_frameworks` count |

### 23. Slide-4 validation recoveries · [LIVE, 2026-09-03]
| Token | Source |
|---|---|
| `U_RES` | `list_discovered_resources{first:1}` → `discoveredResources.totalCount` |
| `CLI` | `list_cicd_scans{created_after:"<today-30d>", limit:1}` (codesec) → `cicdScans.totalCount` |
| `CL_DP` | derived = `DS_P` (DSPM coverage %) |
| `CL_REDA` | derived = `100` if Red Agent is active (`RA_DAST`>0 or `RA_WC`>0), else `0` |
| `CL_UVMP` | derived = share of `VS_*` toggles enabled (from `get_vulnerability_assessment_settings`) |

### 33. Slide-6 corrections (review, 2026-09-03)
- `F_IR` (inventory mgmt rules) = `list_inventory_rules{}` **totalCount** = ALL rules (N), NOT `creator_type:USER` (N).
- `F_TR` (resource tag rules) = `list_inventory_rules{enabled:true}` vs `{enabled:false}` = "N / 0" (all inventory rules; the `TAG_ENFORCEMENT` subtype alone is only 7 — the page's "tag rules" = all inventory rules).
- `F_PP` (user posture policies) = **`cspm.list_cloud_configuration_rules{created_by_type:["USER"]}.totalCount`** (N; page shows ~N — the ~N gap is likely TERRAFORM/IaC-only rules). NOT `list_controls` (N, wrong scope).
- `F_AR` (automation rules) = `automation.list_automation_rules{enabled:true}`/`{enabled:false}` = "N / N" (sums to the N the page shows; the MCP CAN split even though the page can't sort by status). ✓ correct.
- **`F_WF` (configured workflows N/N) — N/A, precisely grounded (2026-09-03, from `docs.wiz.io/docs/wiz-ai-tools`).** The `automationWorkflows` query DOES exist (scope `read:automation_workflows`; also `automationWorkflowRuns*`), but **no MCP tool wraps it** — the AI-tools catalog exposes only `list_automation_rules` (rules) and `list_workflow_templates` (the pre-built *template catalog*, N items, scope `read:automation_workflow_templates`), NOT configured workflow instances. Probed live: `list_automation_workflows` / `get_automation_workflows` / `list_automation_workflow_runs` all "not available". `automationWorkflows` is a top-level query (not a graph entity), so `execute_graph_query` can't reach it either. Configured workflows are reachable only via the **Terraform `wiz-v2_automation_workflows` data source** / raw GraphQL — outside the MCP tool surface. ⚠️ Do NOT confuse `list_workflow_templates` (catalog) with workflow instances.
- **`F_BE`/`F_WMCP` — no clean source:** `F_BE` (N unique browser-ext performers), `F_WMCP` (N unique MCP performers) are audit-log *unique-performer* counts; `list_audit_log_entries` filters by action but returns no distinct-performer aggregate.

> **Resolving tool reachability (authoritative method, 2026-09-03).** `discover` is incomplete AND the
> callable surface is permission-gated (Wiz troubleshooting: *"a missing tool = a missing permission;
> users only see tools their permissions allow"*). So "tool not available" can mean *nonexistent* OR
> *scope-gated*. To settle any token: (1) check **`docs.wiz.io/docs/wiz-ai-tools`** — every MCP tool with
> its required **Scopes**; a tool listed there but absent from `execute` is a scope you can grant. (2) map
> the scope → its GraphQL queries via **`docs.wiz.io/docs/graphql-scopes-to-apis`**. (3) if no tool row
> exists on the page, the capability isn't in the MCP surface (may still be in the Terraform provider /
> raw GraphQL). Then probe the name to confirm.

### 32. Workload scans (`WS_T`/`WS_F`/`WS_S`/`WS_P`/`WS_S1`) — REWRITTEN 2026-09-03 · see `docs/wiz-scan-counts.md`
**SUPERSEDES the old "failures only / use summarize_scan_failures" approach** (that tool is now DO-NOT-USE —
it merges data+workload failures). Workload scan status counts ARE fully available via
`execute_graph_query` on `SECURITY_TOOL_SCAN` with `dataSource_name:["Wiz Workload Scanner"]` — success
is capped at Nk so it MUST be partitioned by `scannedResourceType` with the **residual `NOT_EQUALS`
technique** (proves exhaustiveness; sampling misses small types — `Workstation`=2). Validated live 2026-09-03:
- `WS_T` (total) = Success+Skipped+Error = **N** (unpartitioned total caps at Nk — use the partitioned sum).
- `WS_F` (failed) = `status:["ScanStatusError"]` = **N** (uncapped direct).
- `WS_S` (skipped) = `status:["ScanStatusSkipped"]` = **N** (uncapped direct).
- `WS_P` (coverage) = Success/Total = N/N = **N%** (Success from the residual-proven partition).
- `WS_S1` (top failure reason) = partition errors by `scannedResourceType`, sample `statusDetails`, exact-count
  the top message = **"Storage account is locked for modification" (N)** (failures are spread thin).

⚠️ NOTE these are the *current-entity* `SECURITY_TOOL_SCAN` model (latest scan per resource), NOT the
Settings→Workload Scan Log *event* counts. Also `Endpoint`+`RepositoryBranch` scans file under the Workload
Scanner but are exposure/VCS scans — so this boundary ≠ the scan-log page's `dataScan:false`. Old tokens
`WS_TF`/`WS_S2`/`WS_S3`/`WS_SK` are orphaned by the new slide-5 layout.

### 31. ⚠️ System-Health severity counts — query EACH severity SEPARATELY (review, 2026-09-03)
`list_system_health_issues` **mislabels `criticalSeverityCount`/`highSeverityCount` when you pass
`severity:["CRITICAL","HIGH"]` together** (combined gave N/N; the truth is N/N). Always issue
one call per severity:
- `SHI_C` = `{severity:["CRITICAL"], status:["OPEN"]}` → `criticalSeverityCount` (N ✓ exact match)
- `SHI_H` = `{severity:["HIGH"], status:["OPEN"]}` → `highSeverityCount` (N)
- `SHI_R_C` = `{severity:["CRITICAL"], status:["RESOLVED"]}` (N all-time; the page's "(Nd)" is a subset — MCP has no date window)
- `SHI_R_H` = `{severity:["HIGH"], status:["RESOLVED"]}` (N all-time)
`status:["OPEN"]` already excludes IGNORED. **The SHI breakdown (`SHI_CC`/`SHI_RC`/…) used the same
combined query and likely needs re-checking per-severity too.**

### 30. Slide-4 validation corrections (review, 2026-09-03)
- `RA_WC` (Web Crawler endpoints) = **`attack_surface.list_api_endpoints{is_ai_generated:true}.totalCount`** (e.g. N).
  NOT `list_endpoint_attack_surfaces{scan_source:["RECON"]}` (=all recon endpoints, ~Nk — wrong).
- `RA_DAST` = `list_attack_surface_findings{is_ai_powered:true, finding_type:["EXPLOITABILITY_VALIDATION"]}` (N) ✓
- `RA_TOTS` (total monthly Red Agent scans) = **`attack_surface.list_system_activity_logs{activity_type:["RED_AGENT_SCAN"], started_after:<today-30d>}.totalCount`** (e.g. N — actual scan activities in the last N days). More accurate than the original deck's proxy (`RA_WC+RA_DAST+RA_SI+dast-issues` ≈ N).
- `TI` (container images) = **RUNNING images** (matches the Wiz page's "running images = true" default):
  `container_security.list_container_images{property_name:"lifecycleStagesV2_cloud_detected", property_boolean_value_filter:true}.totalCount`
  (e.g. N). NOTE: `lifecycleStagesV2_runtime_detected` gives a smaller subset (N); `cloud_detected` is the
  "running" view. (The original deck used *all* container images ≈N — the running view was chosen.)
- `R_TOT` (container registries) = **no clean MCP source.** Graph `CONTAINER_REGISTRY` overcounts (~N; AWS ECR
  is modeled per-repository). `list_container_images_grouped{group_by:["CONTAINER_REGISTRY"]}.totalCount` gives
  ~N registries-with-images (closer to the page's N but not exact). → `Not available via MCP` unless a
  registries-with-images proxy is acceptable.
  **BUT the `R_1..6`/`RC_1..6` TYPE LADDER DOES populate — do NOT leave it N/A** (live-validated 2026-09-04):
  `list_cloud_resources_grouped{type_equals:["CONTAINER_REGISTRY"], group_by:["NATIVE_TYPE"], first:8}` →
  top nodes ranked by count. `R_n` = friendly name of `nativeType` (map: `containerRegistry`→ECR,
  `artifactregistry#repository`→GAR, `Microsoft.ContainerRegistry/registries`→ACR,
  `publicContainerRegistry`→ECR Public, `ghcrContainerRegistry`→GHCR, `container#registry`→GCR);
  `RC_n` = `analytics.resources.count`. Caveat: counts are repo-level (AWS ECR modeled per-repo, so its
  count is inflated) — fine for the *ranking/breakdown* the ladder shows; only the R_TOT **total** is unreliable.

### 24. Per-status scan splits via `execute_graph_query` · [LIVE, slide-5 validation, 2026-09-03] ⭐
The big recovery: `SECURITY_TOOL_SCAN` entities carry `status`, `scannedResourceType`, and
`dataSource_name`. Query them with `execute_graph_query` and read `graphSearch.totalCount`. The
**failed/skipped/total slices are small enough to stay under the Nk cap** (`maxCountReached:false`),
so per-status counts are ACCURATE even on large tenants — this is what makes the scan blocks work.

Base query (fill `<STATUS>` / `<RESOURCE_TYPE>`):
```json
{"type":["SECURITY_TOOL_SCAN"],"select":true,"where":{
  "dataSource_name":{"EQUALS":["Wiz Workload Scanner"]},
  "status":{"EQUALS":["<STATUS>"]},
  "scannedResourceType":{"EQUALS":["<RESOURCE_TYPE>"]}}}
```
- `<STATUS>`: `ScanStatusError` (failed), `ScanStatusSkipped`, `ScanStatusSuccess`; omit for total.
- `<RESOURCE_TYPE>`: `SecurityToolScanScannedResourceTypeContainerImage` (RCI),
  `...VirtualMachineImage` (VMI), `...NonOSDisk` (NON). Omit `scannedResourceType` for the whole
  workload total (`WS`).

| Token | Query | 
|---|---|
| `RCI_T`/`RCI_F`/`RCI_S` | ContainerImage: total / Error / Skipped |
| `VMI_T`/`VMI_F`/`VMI_S` | VirtualMachineImage: total / Error / Skipped |
| `NON_T`/`NON_F`/`NON_S` | NonOSDisk: total / Error / Skipped |
| `WS_F`/`WS_SK` | Workload Scanner (no resource type): Error / Skipped |
| `RCI_C`/`VMI_C`/`NON_C` | derived: `(T − F − S) / T` |
| `WS_P` | derived: `(WS_T − WS_F − WS_SK) / WS_T` (`WS_T` from `get_license`) |
| `CL_CP`=`WS_P`, `CL_DP`=`DS_P`, `CL_NRVP` | `CL_NRVP` = combined `(RCI+VMI+NON) success ÷ total` |

NOTE: use the graph `SECURITY_TOOL_SCAN` `totalCount` for `RCI_T` (current scan entities, e.g. N),
NOT `get_license`'s registry-image count (that is *cumulative* scans, e.g. N — a different metric,
wrong denominator for a coverage %).

### Resolved System-Health Issues (`SHI_R_C`/`SHI_R_H`) — partial
`list_system_health_issues{status:["RESOLVED"],severity:["CRITICAL"|"HIGH"]}` returns resolved
counts (e.g. N / N), but the tool has **no date filter**, so it is *all-time* resolved, not the
deck's **(Nd)** window. Populate only if all-time is acceptable; otherwise leave N/A.

### 29. Inventory rules + integrations + resolved-SHI + tenant-age · [LIVE, 2026-09-03]
| Token | Source |
|---|---|
| `F_IR` | `inventory.list_inventory_rules{creator_type:["USER"], limit:1}` → `totalCount` (e.g. N) |
| `F_TR` | `list_inventory_rules{rule_type:["TAG_ENFORCEMENT"], enabled:true}` vs `{enabled:false}` → "on / off" (e.g. 7 / 0). (`rule_type` enum: CUSTOM / TAG_ENFORCEMENT / AGENT_COVERAGE — note `AGENT_COVERAGE` rules exist too.) |
| `IA_1..N` | `success.list_integrations{status:["ACTIVE"]}` node `name`s (names only, not recency-ordered) |
| `IR_1..N` | the matching integration's **`status`** field (ACTIVE/PENDING/INACTIVE/FAILURE/AUTH_REQUIRED) — repurposed from "last activity date" (dates aren't exposed; status is). |
| `SHI_R_C`/`SHI_R_H` | `list_system_health_issues{status:["RESOLVED"],severity:[...]}` counts (e.g. N/N) — **ALL-TIME; the deck label says "(Nd)" but MCP has no date window, so this overstates a true N-day figure.** |
| `CUS_NOD` | **proxy** = today − MIN(`startAt`) across `list_licenses{license_status:["ACTIVE","PENDING","TERMINATED","EXPIRED"]}` (no true tenant-creation date; e.g. earliest 2026-06-17 → ~N days) |

**License statuses & history (important):** `list_licenses` defaults to `ACTIVE` only. Pass
`license_status:["ACTIVE","PENDING","TERMINATED","EXPIRED"]` to see **future** (PENDING renewals, booked
years out) and **past** (TERMINATED/EXPIRED) terms. `get_license{start_at,end_at}` returns a daily
`dataPoints` consumption time series — but it is **clamped to that license's own term** (query the older
license id for older history), future PENDING windows return **all-zero** rows (contracted quota, not a
forecast), today's point is partial, and payloads are N-248KB (jq the `dataPoints`, don't inline).

### 28. Slide 3-4 derived / probe recoveries · [LIVE, 2026-09-03]
| Token | Value basis |
|---|---|
| `CL_UVMP` | `0%` — license `averageUvmWorkloadCount == 0` (UVM not adopted) |
| `CL_ASMP` | `100%` if Advanced ASM active (Red Agent findings exist → advanced ASM on), else 0 |
| `CL_SUP` | `100%` if SaaS connectors exist (`list_subscriptions{cloud_provider:["Microsoft365","Okta","Salesforce","GoogleWorkspace","Slack","MongoDBAtlas"]}` totalCount>0), else `0%` |
| `CON_WOS` | derived estimate = `SENSOR_COVERAGE_PERCENTAGE × averageComputeWorkloadCount` (e.g. 7% × N ≈ N) — flag as estimate |
| `F_BE` | **N/A** — distinct-user count not cleanly available (metric empty/unreliable; audit path needs `admin:audit`). Mark `Not available via MCP`. |
| `F_DR` | discovery is *active* (`list_service_catalog` services carry `promotedBy` discovery rules) but the rule COUNT isn't exposed → leave N/A or report "active" |

### 27. Agent enablement via FUNCTIONAL PROBES (`F_GA`/`F_BA`/`F_RA`) · [LIVE, 2026-09-03] ⭐
**Pattern:** when a config *toggle* isn't exposed over MCP, probe for the feature's *output* instead.
The AI-agent enablement flags aren't reliably readable as settings, but you can prove each agent is
actually running by finding its analyses. **Run this in a subagent — the analysis payloads are NK+
tokens each — short-circuit at the first hit and return only a boolean.**

- **`F_GA` (Green Agent)** = "Enabled" if BOTH: (a) `list_preview_migration_hub_items{enabled:true}`
  contains `"id":"GREEN_AGENT"` with `enabled:true`, AND (b) a functional hit —
  `list_issues{severity:["CRITICAL"],status:["OPEN"],first:N}` → loop `get_green_agent_analysis{issue_id}`
  until `aiRemediationAnalysis` is non-null (one null is normal — custom-control issues lack it, so
  sample up to N). The flag alone is NOT sufficient (the tenant AI-settings switch isn't MCP-visible).
- **`F_BA` (Blue Agent)** = "Enabled" via functional probe ONLY (there is NO `BLUE_AGENT` flag).
  `soc.list_detections{type:["GENERATED_THREAT"], order_by_field:"CREATED_AT", order_by_direction:"DESC", first:N}`
  → take each detection's `issue.id` → `get_blue_agent_analysis{issue_id}` → check
  `issue.threatDetectionDetails.aiAnalysis.status == "COMPLETED"`. **Order by CREATED_AT, not severity**
  (an old pre-enablement threat never gets an analysis → false NO). "Running but not finished" is a
  real third state.
- **`F_RA` (Red Agent)** = "Enabled" if Red Agent findings exist (`RA_DAST`>0 or `RA_WC`>0).

> This "probe-for-output" pattern likely also recovers other unexposed toggles — `F_DR` (discovered
> service-catalog entries), `F_IR`/`F_TR` (governed inventory / tag-applied resources), and possibly
> some slide 17/N scanner-config toggles ("is X scanning on?" → "do X scans exist?").

### 26. Slide-6 adoption/governance recoveries · [LIVE, 2026-09-03]
| Token | Source |
|---|---|
| `U_TOT` | `settings.list_users{status:["DELETED"]}` → `totalCount` (non-deleted portal users, e.g. N) |
| `U_ENG` | derived: `U_ACT / U_TOT` (e.g. N/N = N%) |
| `F_AR` / `F_WF` | `automation.list_automation_rules{enabled:true}` vs `{enabled:false}` → "on / off" (e.g. N / N) |
| `F_WMCP` | **N/A** — `list_integrations{type:["WIZ_MCP"]}` counts *integrations*, not distinct MCP *users* (the deck metric); no performer aggregate exists. Mark `Not available via MCP`. |
| `F_PP` | `issues.list_controls{created_by:["USER"]}` → `totalCount` (user-created policies, e.g. N) |
| `F_RA` | "Enabled" if Red Agent active (`RA_DAST`>0) |
| `IA_1..N` | `success.list_integrations` node names — **names only; no activity date** |
| `F_BE` | **N/A** — see `F_BE` above: distinct-user metric not cleanly available. Mark `Not available via MCP`. |

Still NA on this tenant: `IR_1..N` (integration last-activity dates — not exposed), `F_BA`/`F_GA`
(Blue/Green agent enablement), `F_IR` (inventory mgmt rules), `F_DR` (discovery rules),
`F_TR` (resource tag rules).

### 25. License usage — the 4 main licenses (slide 4, `LU_*`) · success · [LIVE, 2026-09-03]
Call `get_license` with `fetch_quota_usage:true` (and `list_licenses` to get the SKU ids). For each
of the 4 licenses, report **used vs quota** in that license's native unit (format: "used / quota (pct%)").
| Token | License | Unit | Source |
|---|---|---|---|
| `LU_ADV` | Advanced (or the ONE bundle) | workloads | `get_license` → `totalWorkloadCount` / `licensedWorkloadQuota` (e.g. N / N = N%) |
| `LU_CODE` | Wiz Code | developers | `get_license` on the CODE SKU → `quotaUsage` vs quota |
| `LU_DEFEND` | Wiz Defend | ingestion units | `get_license` on the DEFEND SKU → `quotaUsage` vs quota |
| `LU_SENSOR` | Wiz Sensor | deployed sensors / coverage | `SENSOR_COVERAGE_PERCENTAGE` metric (e.g. 7%), or `get_license` on the SENSOR SKU |
NOTE: if the tenant doesn't hold a given license (its SKU absent from `list_licenses`), that token is
`N/A`. The template already prints the unit word ("Developers", "Units"), so the value is just the
number/percent.

### 21. `graph_search` (TECHNOLOGY → SERVICE_ACCOUNT traversal) · inventory · [GRAPH]
`PI_T1_*`, `PI_T2_*`, `PI_T3_*` (N tokens): third-party technologies detected via their service accounts,
tiered by service-account count, with first/last-seen dates. Requires a Security-Graph entity query.

### 22. Small direct/derived wins · [LIVE/SCHEMA]
| Token | Source |
|---|---|
| `Customer` | input (customer name the user provides) |
| `AI_IF` | `list_issues_grouped{group_by:"RESOURCE", security_risk:["wct-id-1998"], type:["CLOUD_CONFIGURATION","TOXIC_COMBINATION"], severity:[...]}` — AI inventory findings (or `list_posture_issues`) |
| `AI_MF` | `list_issues{security_risk:["wct-id-1998"]}` totalCount — AI misconfiguration findings |
| `CC_TOT` | `list_champion_center_modules` (count of journey items) |
| `C_OTH_NAMES` | distinct non-AWS/Azure/GCP `cloudProvider` names from `list_subscriptions` |
| `CON_K8S` | `list_deployments{type:["KUBERNETES_CONNECTOR"]}` totalCount — [LIVE 2026-09-03] |
| `CON_TOT` | `list_deployments` — sum of CLOUD_CONNECTOR + KUBERNETES_CONNECTOR + REGISTRY_CONNECTOR + VERSION_CONTROL_CONNECTOR totalCounts — [LIVE 2026-09-03] |
| `SERVERLESS_CT_COUNT` | `list_cloud_resources_grouped{type_equals:["CONTAINER_SERVICE"], group_by:["TYPE"]}` → `nodes[0].analytics.resources.count` (Fargate/Cloud Run services) — [LIVE, slide-3 validation] |

---

## NOT available via MCP — write `Not available via MCP`

**Config toggles (slides N/N) — the structural gap.**
- **All Data-Security-Scanner toggles (`DSS_*`, ~N):** `dataScannerSettings` has no MCP tool.
- **Most Workload-Scanner toggles (`WS_*`):** only `WS_NONOS` (+ `WS_EXCL`) reachable; `WS_VM`,
  `WS_AFIM`, `WS_NRT`, `WS_NRTW`, `WS_LAMB`, `WS_LSAIL`, `WS_CMK`, `WS_TVOL`, `WS_ADE1`, `WS_ADE2`,
  `WS_CIGS`, `WS_TAGS`, `WS_SNAP` are not.
- **Most ASM-Scanner toggles (`ASM_*`):** the scanner-settings block (mode, advanced scan sources,
  risk/rule toggles, exposure level) is not exposed — `list_attack_surface_rules` is the detection-rule
  catalog, not the settings. `ASM_MODE`, `ASM_ON`, `ASM_RECON`, `ASM_RS`, `ASM_CODE`, `ASM_SAAS`,
  `ASM_API`, `ASM_CUST`, `ASM_DAST`, `ASM_CRED`, `ASM_MISC`, `ASM_HPT`, `ASM_VEXP`, `ASM_EAR`,
  `ASM_DATA`, `ASM_SEC`, `ASM_SV`, `ASM_VULN`, `ASM_EXPL`.
- `VS_LVULN` (Linux latest-kernel vulns) — the one `VS_*` toggle not in the settings response.

**Per-status scan splits — RECOVERED (see call N).** `WS_F`/`WS_SK`/`WS_P`, `RCI_*`, `VMI_*`,
`NON_*` are all reachable via `execute_graph_query` on `SECURITY_TOOL_SCAN` (the failed/skipped/total
slices stay under the Nk cap). No longer a gap.

**Analytics / history not exposed by a curated tool:**
- `s1d` (N-day security-score trend), `MTTR_O` (tenant-wide MTTR), `AVG_AGEC`/`AVG_AGEH` (issue age),
  `RA_TOTS` (total monthly Red Agent scans), `RT` (resolved-threats-90d window).

**Slide-4 "Cloud Advanced" derived block (`CL_*`) — partial (validated 2026-09-03):**
- Recoverable (see call N): `CL_DP` (=`DS_P`), `CL_REDA` (Red-Agent-active→100), `CL_UVMP` (share of
  `VS_*` enabled).
- Still NA — inputs unreachable: `CL_CP` (compute %, needs workload success ratio `WS_P`),
  `CL_ASMP` (Advanced ASM %, needs ASM scanner mode), `CL_WOP` (WizOS %, no WizOS count),
  `CL_NRVP` (non-OS/registry/VM %, per-status splits), `CL_SUP` (SaaS %, needs SaaS scanner state).
- Container-lifecycle counts `CL_BLD`/`CL_CLD`/`CL_CODE`/`CL_DEP`/`CL_RT`/`CL_STR` → NA
  (`LIFECYCLE_STAGE` grouping returns opaque base64 IDs with `name:null`; see correction #8).

**Connector / deployment inventory — RECOVERED (2026-09-03, corrects the earlier "genuine gap").**
The earlier verdict was WRONG: it trusted `discover`, which does NOT list every callable tool. The
unlisted **`list_deployments`** tool executes fine and IS the deployment roster. Params: `type[]`,
`status[]`; ignores `first`; returns N nodes + `deployments.totalCount`. `type` enum includes
`CLOUD_CONNECTOR, KUBERNETES_CONNECTOR, REGISTRY_CONNECTOR, VERSION_CONTROL_CONNECTOR, BROKER,
ADMISSION_CONTROLLER, OUTPOST, SENSOR, KUBERNETES_AUDIT_LOG_COLLECTOR, …`. `status` enum =
`INITIALIZING/DISABLED/ENABLED/UNINSTALLING/UNINSTALLED`. Now **populated** (one call each,
read `totalCount`):
`CON_K8S`=`type:["KUBERNETES_CONNECTOR"]`, `CON_R`=`type:["REGISTRY_CONNECTOR"]`,
`CON_VCS`=`type:["VERSION_CONTROL_CONNECTOR"]`, `CON_TOT`=sum of the 4 connector types,
`CON_DIS`=`status:["DISABLED"]`, `CON_EN`=`status:["ENABLED"]`, `OUT_DEP`=`type:["OUTPOST"]`,
`L_SE`=`type:["SENSOR"]`.
**Still N/A — real limits (not tool-surface):**
- `CON_BRO` (deck label "Connectors - Errored") — the `status` enum has **no `ERROR`/health** value and
  nodes carry no `health`/`errorCode`; only enable-state exists. (The shipped service-account deck
  quietly reused `CON_BRO` for the BROKER *count* = `type:["BROKER"]` — available if you want that
  instead, but it does not mean "errored".)
- `CON_EN` is **enable-state, not connection-health** — labelled as such on the deck.
- `CON_NE`/`CON_WE` (connectors without/with cloud events) — derivable only by inspecting each node's
  `modules[]` (e.g. `EVENT_SCANNER`) across ALL connectors, but `list_deployments` exposes no
  pagination cursor (N-node cap) → not aggregatable.
- `CON_WOS` (sensor *workload* count) — a workload metric, not a deployment count.
> Rule: never conclude "no tool for X" from `discover`; CALL a plausible name and check for
> `tool "X" is not available`. Probe sweep (2026-09-03) found `list_deployments` + `list_automation_rules`
> unlisted-but-real; `list_workflows`, `list_container_registries`, `list_connectors`, all
> workload-scan-log names, browser-ext/MCP-usage names all returned "not available".

**Adoption / governance not exposed:**
- `U_TOT` (total portal users — `get_platform_adoption_metrics` gives only active; check `settings` domain),
  `U_ENG` (needs `U_TOT`), `CUS_NOD` (tenant-creation date), `F_BA`/`F_GA`/`F_RA` (agent enable toggles),
  `F_TR`/`F_DR` (tag/discovery rules), `F_WMCP` (Wiz-MCP users), `F_AR`/`F_WF` (automation on/off — check
  `automation` domain), `IA_*`/`IR_*` (integration last-activity dates), `ROADMAP_TRACKER`,
  `CLI` (Wiz CLI Nd scans), `OUT_DEP`, `CON_WOS`, `L_SE`, `CON_WE`/`CON_NE`.

> These lists are the honest coverage boundary. As Wiz adds MCP tools (esp. for `dataScannerSettings`
> and scan-status ratios), migrate the corresponding rows up into the "Available" section.

---

## 🔬 Systematic N/A reachability pass (2026-09-03) — 5-family sweep

Cross-referenced every remaining N/A token against the AI-tools catalog + live probes. **New
unlisted-but-callable tools discovered:** `list_attack_surface_scan_log_table`,
`list_attack_surface_rules`, `list_endpoint_attack_surfaces`, `list_container_images_grouped`,
`get_nrt_settings` (cspm), `get_ebs_snapshot_scanner_settings`, `get_non_os_disk_scanning_settings`,
`get_vulnerability_assessment_settings`, `list_threats` (soc), `list_hosted_technologies_group_by_value`,
`list_technologies`, `list_imported_assets`.

### RECOVERED → now populated
| Token(s) | Source | Value (2026-09-03) |
|---|---|---|
| `CL_BLD`/`CL_CLD`/`CL_DEP`/`CL_RT`/`CL_STR` | `list_container_images{property_name:"lifecycleStagesV2_<build|cloud|deploy|runtime|store>_detected", property_boolean_value_filter:true}` totalCount | N / N / 0 / N / N |
| `R_TOT` | `list_container_images_grouped{group_by:["CONTAINER_REGISTRY"]}` totalCount | N |
| `RT` | `list_threats{status:["RESOLVED"], resolved_at_in_last_amount:N, resolved_at_in_last_unit:"DurationFilterValueUnitDays"}` totalCount | N |
| `WS_NRT`/`WS_NRTW` | `get_nrt_settings.eventTriggeredScanningSettings.{enabled, workloadScanningEnabled}` | Enabled / Enabled |
| `WS_TVOL` | `get_ebs_snapshot_scanner_settings...workloadScanningUsingTemporaryVolumesSettings.enabled` | Enabled |

### FLAGGED (reachable but imperfect — left N/A pending review)
- `WS_CMK` — readable via `get_ebs_snapshot_scanner_settings.snapshotReencryptionSettings`
  (sharedCMK patterns=null, disableWizKeyCreation=false), but toggle polarity ambiguous.
- `CL_WOP` (~N%) — computed = WizOS image count (`list_hosted_technologies_group_by_value{tech_id:["N"]}` = N) ÷ total images (N); depends on tech_id N = WizOS assumption.
- `L_CL_PCT` (N%) — `list_monitored_metrics{metric_types:["CONTAINER_SECURITY_COVERAGE"]}` is "Daily Kubernetes Security Coverage", a semantic mismatch for "lifecycle coverage".

### CONFIRMED GENUINE GAPS (probed, not assumed)
- **ASM config toggles (slide 17, all `ASM_*`)** — NO attack-surface settings tool exists on the MCP
  surface (`get_attack_surface_settings`/`_scanner_settings`/`get_asm_settings` all absent; settings
  domain = RBAC only). Live *evidence proxies* exist (`list_attack_surface_scan_log_table` source/
  finding_type row counts; `list_attack_surface_rules` enabled flags — enabled=false sweep=0 so no rule
  category disabled; `list_endpoint_attack_surfaces.exposureLevel`) but these are one-directional
  inference, not the literal setting → **left N/A per "real artifact not proxy".** `ASM_MODE`/`ASM_DAST`/
  `ASM_EAR`/`ASM_SV`/`ASM_VULN` have no path at all.
- **Data Security Scanner block (slide 18, all `DSS_*`, N)** — no data-scanner-settings tool exists.
- **Workload toggles `WS_VM`/`WS_AFIM`/`WS_LAMB`/`WS_LSAIL`/`WS_ADE1`/`WS_ADE2`/`WS_CIGS`/`WS_TAGS`** — no tool.
- **`VS_LVULN`** — `get_vulnerability_assessment_settings` exists but has no Linux-kernel-mode field.
- **`CL_CODE`** — `list_container_images` lifecycle enum has no code-stage property.
- **`R_AUT`/`R_CON`/`R_CUS`** — `CONTAINER_REGISTRY` group nodes are opaque (name/type null); no connector-type split.
- **Analytics `s1d`/`MTTR_O`/`AVG_AGEC`/`AVG_AGEH`** — metrics are current-snapshot only; no history/MTTR/
  age tool (the `AVERAGE_AGE` aggregation exists tenant-side but there's no create-metric tool to build it read-only).
- **`F_DR`** (service discovery rules ≠ `list_inventory_rules`), **`ROADMAP_TRACKER`** (only released updates exposed).
- **Slide-19 `PI_*` (all N "Potential Integrations")** — no detected-but-unconfigured-integration tool;
  `list_integrations`=configured only; `list_service_accounts` absent; `list_audit_log_entries`=**N on
  `read:all`** (needs `admin:audit`) AND wrong shape. (Also independently kills the `F_BE`/`F_WMCP` audit path.)
