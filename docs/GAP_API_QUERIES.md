# Wiz Health Assessment — Manual GraphQL for the MCP Gaps

> **Purpose.** The Health Assessment deck is ~60–75% populated by the **Wiz MCP** alone
> (see `SKILL.md` + `docs/MCP_TOKEN_MAP.md`). This runbook covers the **remainder** — the
> metrics the MCP has no tool for — as **pasteable GraphQL** the operator runs in the Wiz
> **GraphQL Sandbox**. It is the "how" companion to `MCP_COVERAGE_GAPS.local.md` (the "what & why").
>
> **Audience.** Someone with **`read:all`** on the target tenant (no service account required).
> **Where to run.** The tenant's GraphQL Sandbox: `https://app.<region>.app.wiz.io/graphql-sandbox`
> (e.g. `us20`, `us1`, `eu1` — read the region from the tenant URL bar).
> **What to do with the output.** Read each value off the JSON response and drop it into the
> corresponding `{{TOKEN}}` cell of the metrics CSV (the same CSV the MCP path writes). Anything
> you skip stays `Not available via MCP` → renders as **N/A**.

> **No tenant data in this file** — only GraphQL query text, so it ships in the public repo for
> end-users who want to self-serve the gaps. Its companion, the gap *inventory*
> (`MCP_COVERAGE_GAPS.local.md` — the "what & why", with per-tenant notes), is kept internal.

---

## Confidence legend

- ✅ **PROVEN** — field path verified against real tenants (carried over from the maintained
  service-account runbook `api-delta-query.md`). Paste as-is.
- ⚠️ **VERIFY** — field path is the best-known shape but **introspect on first run** for the exact
  spelling on this tenant's schema version. Introspection snippet in §8.
- 🖥️ **UI / not in GraphQL** — no query exists; read it off the portal, or derive it.

---

## 1. Coverage map — gap → query → deck tokens

| # | Gap (slide) | Query | Deck tokens | Conf. |
|---|---|---|---|---|
| A | Workload Scanner config (17) | **GQ1** `scannerSettings` + siblings | `WS_VM WS_CMK WS_TVOL WS_LSAIL WS_LAMB WS_CIGS WS_ADE1 WS_ADE2 WS_NRT WS_NONOS WS_EXCL` | ✅ |
| B | DSPM Data-Scanner config (18) | **GQ1** `dataScannerSettings` | `DSS_*` (master + per-source toggles) | ⚠️ |
| C | Vulnerability-Scanner config (18) | **GQ1** `vulnerabilityAssessmentSettings` | `VS_OSPKG VS_WINB VS_GOSTD VS_PIP VS_NPM VS_RHOS VS_EOL VS_MANIF VS_LOCK VS_ARTIF VS_MAVEN VS_JSDEP VS_GRADL` (+ Linux-kernel mode ⚠️) | ✅ / kernel ⚠️ |
| D | Attack-Surface (ASM) config (17) | **GQ1b** `attackSurfaceScannerSettings` | ASM mode + source/detection/risk toggles | ⚠️ |
| E | Posture trend & remediation (12) | **GQ2** `monitoredMetrics` + `issuesTrendV2` | `s1d MTTR_O MTTR_C MTTR_H AVG_AGEC AVG_AGEH` | ✅ |
| F | Configured automation workflows (6) | **GQ3** `automationWorkflows` | `F_WF` | ✅ |
| G | Service-catalog discovery rules (6) | **GQ3** `applicationServiceDiscoveryRules` | `F_DR` | ✅ |
| H | Container **Code**-stage images (15) | **GQ4** `cloudResourcesGroupedByValues` LIFECYCLE_STAGE | `CL_CODE` (+ full stage ladder) | ✅ |
| I | Registry scan-source split (15) | **GQ4** `containerRegistries` by `scanningConfigurationType` | `R_AUT R_CON R_CUS` | ✅ |
| J | Potential Integrations (19) | **GQ5** `graphSearch` TECHNOLOGY | `PI_*` (whole slide) | ✅ |
| K | Connector cloud-events split (3) | **GQ6** `connectors` modules | `CON_NE CON_WE` | ⚠️ |
| L | Sensor workloads (3) | **GQ6** `graphSearch` sensor filter | `CON_WOS` | ⚠️ |
| M | Feature-adoption users (6) | **GQ7** `auditLogEntries` distinct performers | `F_BE F_WMCP` | ⚠️ (perm-gated) |
| N | Runtime sensor **unit** count (3) | 🖥️ License page | `L_SE` | 🖥️ |
| O | Roadmap Tracker items (9) | 🖥️ Portal only | `ROADMAP_TRACKER` | 🖥️ |
| P | "Cloud Advanced" adoption % (4) | 🖥️ Derived from A–D outputs | slide-4 %s | 🖥️ |

> **Timestamps.** Queries with a date window use GraphQL variables. Wiz validates DateTime as
> **RFC3339Nano** — `2026-09-04T00:00:00Z` is **rejected**; you must include fractional seconds
> (`.000Z`). Generate all three at once in your browser console:
> ```js
> JSON.stringify({
>   NOW:            new Date().toISOString(),
>   NOW_MINUS_30D:  new Date(Date.now() - 30*86400000).toISOString(),
>   NOW_MINUS_90D:  new Date(Date.now() - 90*86400000).toISOString(),
> })
> ```

---

## 2. GQ1 — Scanner configuration (Workload + DSPM + Vulnerability)

Covers gaps **A, B, C**. No `issuesV2` here, so it's rate-limit safe. No variables.

```graphql
query WhaGapScannerConfig {
  # ---------- A. Workload Scanner (WS_*) ✅ ----------
  ss: scannerSettings {
    computeResourceGroupMemberScanSamplingEnabled          # WS_CIGS
    virtualMachineImages { enabled scanImagesWithoutInstances }  # WS_VM
    aws {
      snapshotReencryptionSettings { sharedCustomerManagedKeysArnPatterns }  # WS_CMK (count of patterns)
      workloadScanningUsingTemporaryVolumesSettings { enabled }              # WS_TVOL
      lightsailScanningSettings { enabled }                                  # WS_LSAIL
      lambdaSettings { scannedVersionCount }                                 # WS_LAMB (>0 = on)
    }
    azure {
      privateEndpointKeyVaults { enabled }                # WS_ADE1
      privateEndpointKeyVaultsWithFirewall { enabled }    # WS_ADE2
    }
  }
  nod: nonOsDiskScanningSettings { enabled daysInterval }  # WS_NONOS
  et:  eventTriggeredScanningSettings { enabled workloadScanningEnabled }  # WS_NRT
  srt: scannerResourceTagSettings { tags { key value } tagInheritanceEnabled }  # WS custom tags
  sex: scannerExclusionSettings  { tags { key value } }   # WS_EXCL (count of tag exclusions)

  # ---------- C. Vulnerability Assessment (VS_*) ✅  (Linux-kernel mode ⚠️) ----------
  vas: vulnerabilityAssessmentSettings {
    osPackageManagedCodeLibrariesVulnerabilitiesDetectionEnabled  # VS_OSPKG
    windowsManagedVulnerabilitiesDetectionEnabled                 # VS_WINB
    goStandardLibraryVulnerabilitiesEnabled                       # VS_GOSTD
    legacyCodeLibraryExclusionPathsEnabled                        # VS_EXCL (vuln-side)
    ignoreRedHatOpenshiftContainerLibraryVulnerabilities          # VS_RHOS
    pipInstalledPythonLibrariesVulnerabilitiesEnabled             # VS_PIP
    npmInstalledJavascriptLibrariesVulnerabilitiesEnabled         # VS_NPM
    codeLibraries {
      manifestFilesLifecycleStages   # VS_MANIF
      lockFilesLifecycleStages       # VS_LOCK
      artifactsLifecycleStages       # VS_ARTIF
      mavenScopes                    # VS_MAVEN
      npmScopes                      # VS_JSDEP
      gradleScopes                   # VS_GRADL
    }
    endOfLifeTechnologies { upcomingDetectionEnabled upcomingDetectionDays }  # VS_EOL
    # ⚠️ Linux installed-vs-running kernel scan mode: introspect this type for a
    #    `kernel*` / `linuxKernel*` field (see §8); not present on all schema versions.
  }

  # ---------- B. DSPM / Data Scanner config (DSS_*) ⚠️ ----------
  # The Azure private-endpoint sub-flags are PROVEN. The per-source master toggles
  # (Buckets / DynamoDB / Data Warehouses / IaaS-PaaS DBs / Serverless / Snowflake /
  # BigQuery / Virtual Drives / VM Disks / Shadow Data / AI sources) vary by schema
  # version — introspect `DataScannerSettings` (§8) and add the fields your tenant exposes.
  dss: dataScannerSettings {
    azureStorageAccountConfig {
      privateEndpointGeneralConfig       { enabled }   # DSS_AZ1
      privateEndpointWithFirewallConfig  { enabled }   # DSS_AZ2
    }
    azureCosmosDbConfig {
      privateEndpointGeneralConfig       { enabled }   # DSS_CDBAZ1
      privateEndpointWithFirewallConfig  { enabled }   # DSS_CDBAZ2
    }
    # ⚠️ add per-source toggles here once confirmed via introspection, e.g.:
    # buckets { enabled }  dynamoDb { enabled }  ...
  }
}
```

**How to read it → tokens**

| Response path | Token | Render |
|---|---|---|
| `ss.virtualMachineImages.enabled` | `WS_VM` | Enabled/Disabled |
| `ss.aws.snapshotReencryptionSettings.sharedCustomerManagedKeysArnPatterns.length` | `WS_CMK` | count |
| `ss.aws.workloadScanningUsingTemporaryVolumesSettings.enabled` | `WS_TVOL` | Enabled/Disabled |
| `ss.aws.lightsailScanningSettings.enabled` | `WS_LSAIL` | Enabled/Disabled |
| `ss.aws.lambdaSettings.scannedVersionCount > 0` | `WS_LAMB` | Enabled/Disabled |
| `ss.computeResourceGroupMemberScanSamplingEnabled` | `WS_CIGS` | Enabled/Disabled |
| `ss.azure.privateEndpointKeyVaults.enabled` / `…WithFirewall.enabled` | `WS_ADE1` / `WS_ADE2` | Enabled/Disabled |
| `et.enabled` | `WS_NRT` | Enabled/Disabled |
| `nod.enabled` (+`daysInterval`) | `WS_NONOS` | `Enabled (Nd)` |
| `sex.tags.length` | `WS_EXCL` | `N tag-based exclusions` |
| each `vas.*` boolean | `VS_*` | Enabled/Disabled |
| each `vas.codeLibraries.*` list | `VS_MANIF/LOCK/ARTIF/MAVEN/JSDEP/GRADL` | comma-joined or `None` |
| `vas.endOfLifeTechnologies.upcomingDetectionEnabled` | `VS_EOL` | `Enabled (Nd)` |
| `dss.azure*Config.*.enabled` | `DSS_AZ1/AZ2/CDBAZ1/CDBAZ2` | Enabled/Disabled |

---

## 3. GQ1b — Attack Surface (ASM) configuration ⚠️

Covers gap **D** (slide 17). The ASM settings block is not in the service-account runbook, so
**introspect first** (§8) for the exact root — candidates: `attackSurfaceScannerSettings`,
`externalScanSettings`, `asmSettings`. Once confirmed, pull:

```graphql
query WhaGapAsmConfig {
  asm: attackSurfaceScannerSettings {   # ⚠️ confirm root name via introspection
    mode                                 # Basic vs Advanced
    enabledSources                       # Reconnaissance / Runtime Sensor / Code / SaaS / API / Custom Targets
    detectionRules {                     # DAST / Default Creds / Misconfig / High-Profile Threats / Vuln Exploitability / Early-Access
      name enabled
    }
    riskSettings {                       # Vulnerability / Secret / Secret Validation / Sensitive Data
      vulnerability { enabled }
      secret { enabled }
      secretValidation { enabled }
      sensitiveData { enabled }
    }
    applicationEndpointExposurePolicy    # exposure-level policy
  }
}
```

If the root doesn't resolve, ASM config stays **N/A** (documented gap D) — the deck degrades gracefully.

---

## 4. GQ2 — Posture trend & remediation analytics ✅

Covers gap **E** (slide 12 — the "are we improving / how fast do we fix" KPIs). Two date windows.

```graphql
query WhaGapPostureTrend(
  $scoreStart: DateTime!   # = {{NOW_MINUS_90D}}   90-day score trend
  $scoreEnd:   DateTime!   # = {{NOW}}
  $mttrStart:  DateTime!   # = {{NOW_MINUS_30D}}   MTTR / issue-age window (matches tenant widget)
  $mttrEnd:    DateTime!   # = {{NOW}}
) {
  # ---------- 90-day Security-Score trend → s1d ----------
  secScore: monitoredMetrics(first: 5, filterBy: {type: [SECURITY_SCORE], builtin: true}) {
    nodes {
      id name type
      dataPoints(startDate: $scoreStart, endDate: $scoreEnd, timeInterval: DAY) { time value }
    }
  }

  # ---------- Threat MTTR (mirrors the tenant MTTR widget) → MTTR_O/C/H ----------
  # MTTR_O = mttr.total / 86400 (days). With interval DAY, `total` = latest day's resolved cohort.
  mttr: issuesTrendV2(
    filterBy: { type: [THREAT_DETECTION] }
    type: MTTR
    startDate: $mttrStart, endDate: $mttrEnd
    interval: DAY
  ) { total dataPoints { time totalValue criticalSeverityValue highSeverityValue } }

  # ---------- Average open issue age → AVG_AGEC / AVG_AGEH ----------
  avgAge: issuesTrendV2(
    type: AVERAGE_ISSUE_AGE
    startDate: $mttrStart, endDate: $mttrEnd
    interval: ALL_RANGE, intervalType: RELATIVE
  ) { dataPoints { criticalSeverityValue highSeverityValue } }
}
```

**Variables**
```json
{ "scoreStart": "{{NOW_MINUS_90D}}", "scoreEnd": "{{NOW}}",
  "mttrStart": "{{NOW_MINUS_30D}}", "mttrEnd": "{{NOW}}" }
```

**How to read it → tokens**

| Response path | Token | Compute |
|---|---|---|
| `secScore.nodes[0].dataPoints[last].value − dataPoints[0].value` | `s1d` | signed delta, 1 dp (e.g. `+3.2`) |
| `mttr.total / 86400` | `MTTR_O` | days, 1 dp (fallback `dataPoints[0].totalValue/86400`) |
| `mttr.dataPoints[last].criticalSeverityValue / 86400` | `MTTR_C` | days |
| `mttr.dataPoints[last].highSeverityValue / 86400` | `MTTR_H` | days |
| `avgAge.dataPoints[0].criticalSeverityValue / 86400` | `AVG_AGEC` | days |
| `avgAge.dataPoints[0].highSeverityValue / 86400` | `AVG_AGEH` | days |

> ⚠️ `2026-…Z` without `.000` → `"DateTime should be RFC3339Nano formatted string"`. Always `.000Z`.
> ⚠️ Med/low threats auto-expire ~90d, so daily MTTR can pin near `7,776,000s` (=90.0d);
> critical/high are the real signal.

---

## 5. GQ3 — Adoption & governance ✅

Covers gaps **F, G** (slide 6). No variables.

```graphql
query WhaGapAdoption {
  # F_WF — configured automation WORKFLOWS (distinct from automation RULES the MCP already returns)
  wfOn:  automationWorkflows(filterBy: {enabled: true})   { totalCount }
  wfOff: automationWorkflows(filterBy: {enabled: false})  { totalCount }
  # NOTE: if wfOff = 0 despite disabled workflows existing, retry with {status: [DISABLED]}.

  # F_DR — Service-Catalog discovery rules
  drTotal: applicationServiceDiscoveryRules(first: 1) { totalCount }
}
```

**Read:** `F_WF = "{wfOn} on / {wfOff} off"`, `F_DR = drTotal.totalCount`.

> **"Workflows are currently not supported" error:** some tenants gate `automationWorkflows`.
> If you hit it, `F_WF` stays **N/A** (gap F) — the API exists (`automationWorkflows`, Terraform
> `wiz-v2_automation_workflows`) but is not enabled on that tenant.

---

## 6. GQ4 — Container lifecycle & registry scan-source ✅

Covers gaps **H, I** (slide 15). No variables.

```graphql
query WhaGapContainerDetail {
  # H. Full image lifecycle ladder — includes the CODE stage the MCP omits → CL_CODE
  imgLifecycle: cloudResourcesGroupedByValues(
    filterBy: { type: {equals: ["CONTAINER_IMAGE"]} }
    groupBy:  { fields: [LIFECYCLE_STAGE] }
    first: 20
  ) { nodes { lifecycleStage analytics { resources { count } } } }

  # I. Registry scan-source split → R_AUT / R_CON / R_CUS
  regAuto:  containerRegistries(first: 1, filterBy: {scanningConfigurationType: [AUTOMATIC], hasDeployment: true}) { totalCount }
  regConn:  containerRegistries(first: 1, filterBy: {scanningConfigurationType: [CONNECTOR], hasDeployment: true}) { totalCount }
  regCust:  containerRegistries(first: 1, filterBy: {scanningConfigurationType: [CUSTOM],    hasDeployment: true}) { totalCount }
  # ⚠️ confirm the scanningConfigurationType enum spellings via introspection if any returns null.
}
```

**Read:** in `imgLifecycle.nodes[]`, find `lifecycleStage == "CODE"` → its `analytics.resources.count`
= `CL_CODE` (the other nodes fill `CL_CLD/STR/RT/BLD/DEP` if you want the full ladder).
`R_AUT = regAuto.totalCount`, `R_CON = regConn.totalCount`, `R_CUS = regCust.totalCount`.

---

## 7. GQ5 — Potential Integrations (slide 19) ✅

Covers gap **J** — the whole slide 19 (third-party tools detected but not yet connected to Wiz,
tiered by prevalence, with service-account counts + first/last-seen). This is the highest-value gap
(land-and-expand). Two passes: totals+active (GQ5a), and the per-tech timeline (GQ5b, optional).

### GQ5a — totals + active subset (one paste)

```graphql
query WhaGapPiCombined {
  q4a_totals: graphSearch(
    first: 500, projectId: "*", quick: false
    query: {
      select: true, type: [TECHNOLOGY]
      where: { deploymentModel: {EQUALS: ["Cloud service"]}, name: {DOES_NOT_CONTAIN: ["Wiz"]} }
      relationships: [{
        type: [{type: HAS_TECH, reverse: true}]
        with: {
          select: true, type: [SERVICE_ACCOUNT], aggregate: true
          where: {externalOwners: {IS_SET: true}}
          relationships: [{
            type: [{type: CONTAINS, reverse: true}]
            with: { type: [SUBSCRIPTION, CLOUD_ORGANIZATION], where: {name: {DOES_NOT_START_WITH: ["Discovered"]}} }
          }]
        }
      }]
    }
  ) { nodes { aggregateCount entities { id name type properties } } }

  q4b_active: graphSearch(
    first: 500, projectId: "*", quick: false
    query: {
      select: true, type: [TECHNOLOGY]
      where: { deploymentModel: {EQUALS: ["Cloud service"]}, name: {DOES_NOT_CONTAIN: ["Wiz"]} }
      relationships: [{
        type: [{type: HAS_TECH, reverse: true}]
        with: {
          select: true, type: [SERVICE_ACCOUNT], aggregate: true
          where: { externalOwners: {IS_SET: true}, inactiveInLast90Days: {EQUALS: false} }
          relationships: [{
            type: [{type: CONTAINS, reverse: true}]
            with: { type: [SUBSCRIPTION, CLOUD_ORGANIZATION], where: {name: {DOES_NOT_START_WITH: ["Discovered"]}} }
          }]
        }
      }]
    }
  ) { nodes { aggregateCount entities { id name type properties } } }
}
```

### GQ5b — per-tech SA timeline (optional; drives first/latest-seen + NEW badges)

```graphql
query WhaGapPiDates($after: String) {
  graphSearch(
    first: 1000, projectId: "*", quick: false, after: $after
    query: {
      select: true, type: [TECHNOLOGY]
      where: { deploymentModel: {EQUALS: ["Cloud service"]}, name: {DOES_NOT_CONTAIN: ["Wiz"]} }
      relationships: [{
        type: [{type: HAS_TECH, reverse: true}]
        with: {
          select: true, type: [SERVICE_ACCOUNT]
          where: {externalOwners: {IS_SET: true}}
          relationships: [{
            type: [{type: CONTAINS, reverse: true}]
            with: { type: [SUBSCRIPTION, CLOUD_ORGANIZATION], where: {name: {DOES_NOT_START_WITH: ["Discovered"]}} }
          }]
        }
      }]
    }
  ) { nodes { entities { id name type properties } } pageInfo { hasNextPage endCursor } }
}
```
**Variables:** first page `{ "after": null }`; if `pageInfo.hasNextPage`, set `{ "after": "<endCursor>" }` and re-run.

**How to read it → tokens**
- Each `nodes[]`: `entities[0].name` = tool name, `aggregateCount` = service-account count, and
  `entities[0].properties.categories` classifies the **Tier** (T1 = CNAPP/CSPM/CIEM/DSPM; T2 = Code/IaC/SAST/SCA;
  T3 = CWPP/CDR/runtime). `q4b_active` counts give the active subset.
- Roll up per tier → `PI_T1_COUNT/SA/AC/PA`, `PI_T2_*`, `PI_T3_*`, `PI_TOT_*`, and per-slot
  `PI_T{1,2,3}_{1..5}` (name/SA/AC/PA/category/last-seen). `properties.lastSeenAt` (or `updatedAt`)
  → `_SEEN`; from GQ5b, min/max `createdAt` per tech → `_FA`/`_LA`, and count in last 90d → `_NC`/`_NF`.
- (This mirrors the tier logic in `api-delta-query.md §4a`; reuse that mapping if you want the exact rollup.)

---

## 8. GQ6 — Connector cloud-events & sensor workloads ⚠️

Covers gaps **K, L** (slide 3). Both need schema confirmation — introspect first.

```graphql
# K. Connectors WITH vs WITHOUT cloud events → CON_WE / CON_NE
# The MCP's list_deployments returns each connector's modules[] but caps at 20 nodes with no
# cursor. Over GraphQL the connectors root paginates. ⚠️ confirm field name + the cloud-events flag.
query WhaGapConnectorEvents($after: String) {
  connectors(first: 100, after: $after) {          # ⚠️ confirm root: connectors / cloudAccountLinks
    totalCount
    nodes {
      id name
      # look for the per-connector cloud-events toggle, e.g.:
      cloudEventsEnabled                            # ⚠️ confirm field
      modules { name enabled }                      # fallback: derive from modules[]
    }
    pageInfo { hasNextPage endCursor }
  }
}
```
**Read:** page through all connectors; `CON_WE` = count with cloud-events on, `CON_NE` = count off.

```graphql
# L. Workloads with the Wiz runtime sensor installed → CON_WOS
query WhaGapSensorWorkloads {
  sensorWorkloads: graphSearch(first: 1, projectId: "*", quick: true, query: {
    type: [VIRTUAL_MACHINE, CONTAINER, SERVERLESS], select: true,
    where: { hasWizSensor: {EQUALS: true} }        # ⚠️ confirm property name (sensor* / wizSensor*)
  }) { totalCount }
}
```
**Read:** `CON_WOS = sensorWorkloads.totalCount`.

---

## 9. GQ7 — Feature-adoption user counts ⚠️ (permission-gated)

Covers gap **M** (slide 6): distinct users of the **Browser Extension** (`F_BE`) and the **Wiz MCP**
(`F_WMCP`) — i.e. unique "performers", not seat count. There is **no distinct-performer aggregate**;
the only path is the audit log, which is `read:all`-gated (often 403) and returns raw entries, not a
rollup. If you have `admin:audit_logs`:

```graphql
query WhaGapAdoptionUsers($after: String, $since: DateTime!) {
  auditLogEntries(first: 500, after: $after, filterBy: { timestamp: {after: $since} }) {
    nodes { action user { id } serviceAccount { id } }
    pageInfo { hasNextPage endCursor }
  }
}
```
**Read:** page all entries in the window; `F_BE` = distinct user IDs on browser-extension actions,
`F_WMCP` = distinct on Wiz-MCP actions. If you get 403 or can't classify the actions, both stay **N/A**.

---

## 10. Manual / not-in-GraphQL (gaps N, O, P) 🖥️

| Token(s) | Where to get it | Note |
|---|---|---|
| `L_SE` (runtime sensor **units**) | Portal → **Settings → Licenses** (unit count on the page) | MCP/GraphQL only expose sensor **groups/deployments**, not licensed units. |
| `ROADMAP_TRACKER` (slide 9) | Portal → **Roadmap Tracker** | API exposes *released* product updates only, not unreleased roadmap items. |
| Slide-4 "Cloud Advanced" %s | **Derive** from A–D outputs | e.g. Advanced-ASM % from GQ1b mode; compute-scan/WizOS/SaaS % need scanner-mode + WizOS count + SaaS-scanner state — fill the inputs from GQ1/GQ1b first, then compute. If an input is N/A, the % is N/A. |

---

## 11. Run instructions

1. **Open the Sandbox** for the tenant's region: `https://app.<region>.app.wiz.io/graphql-sandbox`.
2. **Generate timestamps** with the console snippet (§1) and keep them handy for GQ2.
3. **Paste each query** into the operation editor, put its variables in the **Variables** pane
   (bottom-left), click **▶ Run**. GQ1 → GQ7 are independent; run only the ones whose tokens are
   still `Not available via MCP` in your CSV.
4. **Read each value** off the JSON response using the "How to read it → tokens" tables above, and
   write it into the matching `{{TOKEN}}` cell of the metrics CSV.
5. **Re-render** the deck from the updated CSV (`python3 render_deck.py …`). Cells you didn't fill
   stay **N/A** — which is the honest, correct state for a genuine gap.

**Scope:** `read:all` covers GQ1–GQ6. GQ7 needs `admin:audit_logs`. No service account required.

---

## 12. Introspection snippet (for ⚠️ fields)

When a `⚠️ VERIFY` path returns `null` or a field error, introspect the type on this tenant's schema:

```graphql
query Introspect { __type(name: "DataScannerSettings") { fields { name type { name kind ofType { name } } } } }
```
Swap `"DataScannerSettings"` for `ScannerSettings`, `VulnerabilityAssessmentSettings`,
`AttackSurfaceScannerSettings`, or `Query` (to find a root field's exact name). Match the returned
field names into the query above.

---

*Companion to `MCP_COVERAGE_GAPS.local.md` (the gap inventory) and `docs/MCP_TOKEN_MAP.md` (the
MCP-reachable tokens). Query text ported from the maintained service-account runbook
`agents/tam-cadence-coach/knowledge/api-delta-query.md`; ✅ paths are tenant-verified there, ⚠️ paths
need one introspection pass on first use. No tenant data in this file.*
