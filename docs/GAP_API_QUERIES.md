# Wiz Health Assessment — Manual GraphQL for the MCP Gaps

> **Purpose.** The Health Assessment deck is ~60–75% populated by the **Wiz MCP** alone
> (see `SKILL.md` + `docs/MCP_TOKEN_MAP.md`). This runbook covers the **remainder** — the
> metrics the MCP has no tool for — as **pasteable GraphQL** you run in the Wiz **GraphQL Sandbox**.
> It's the "how" companion to the gap inventory (`MCP_COVERAGE_GAPS.local.md`, the "what & why").
>
> **Audience.** Someone with **`read:all`** on the target tenant (no service account required).
> **Where to run.** The tenant's Sandbox: `https://app.<region>.app.wiz.io/graphql-sandbox`
> (`us20`/`us1`/`eu1` — read the region from the tenant URL bar).
> **What to do with the output.** Read each value off the JSON and drop it into the matching
> `{{TOKEN}}` cell of the metrics CSV. Anything you skip stays `Not available via MCP` → renders **N/A**.

> **No tenant data in this file** — only GraphQL query text, so it ships in the public repo for
> end-users who want to self-serve the gaps. The gap *inventory* (`MCP_COVERAGE_GAPS.local.md`,
> with per-tenant notes) is kept internal.

**Five queries, run only the ones you still need.** Almost everything is parallel aliases in one
round trip — Q1 alone covers ~11 gaps.

| Query | Covers (gaps) | Vars | Conf. |
|---|---|---|---|
| **Q1 — Settings, config & inventory** | Workload/DSPM/Vuln/ASM scanner config, automation workflows, discovery rules, container Code-stage, registry scan-source, connector cloud-events, sensor workloads | none | ✅ / some ⚠️ |
| **Q2 — Posture trend & remediation** | 90-day score trend, MTTR, avg issue age (slide 12) | 4 dates | ✅ |
| **Q3 — Potential Integrations (totals+active)** | slide 19 `PI_*` | none | ✅ |
| **Q4 — Potential Integrations (timeline)** *(optional)* | `PI_*` first/latest-seen + NEW badges | `after` | ✅ |
| **Q5 — Feature-adoption users** *(optional, perm-gated)* | `F_BE`, `F_WMCP` | 1 date | ⚠️ |

**Confidence legend:** ✅ **PROVEN** (field path tenant-verified in the service-account runbook
`api-delta-query.md` — paste as-is) · ⚠️ **VERIFY** (introspect once for the exact spelling on this
tenant — snippet in §7) · 🖥️ **UI / not in GraphQL** (read off the portal, or derive).

> **Timestamps are RFC3339Nano — fractional seconds are mandatory.** `2026-09-04T00:00:00Z` is
> **rejected** (`"DateTime should be RFC3339Nano formatted string"`); `2026-09-04T00:00:00.000Z` works.
> Generate current values in your browser console (**not** the Sandbox):
> ```js
> JSON.stringify({
>   NOW:            new Date().toISOString(),                                  // ...T..:..:...000Z
>   NOW_MINUS_30D:  new Date(Date.now() - 30*86400000).toISOString(),
>   NOW_MINUS_90D:  new Date(Date.now() - 90*86400000).toISOString(),
> })  // every value ends in .NNNZ → RFC3339Nano-valid
> ```

---

## Q1 — Settings, config & inventory  ✅ (some ⚠️)

One round trip, all parallel aliases, **no variables, no `issuesV2`** (rate-limit safe). Covers gaps
A (workload), B (DSPM), C (vuln), D (ASM), F (workflows), G (discovery rules), H (container Code
stage), I (registry scan-source), K (connector cloud-events), L (sensor workloads).

```graphql
query WhaGap1SettingsConfigInventory {
  # ===== A. Workload Scanner (WS_*) ✅ =====
  ss: scannerSettings {
    computeResourceGroupMemberScanSamplingEnabled                          # WS_CIGS
    virtualMachineImages { enabled scanImagesWithoutInstances }            # WS_VM
    aws {
      snapshotReencryptionSettings { sharedCustomerManagedKeysArnPatterns } # WS_CMK (count)
      workloadScanningUsingTemporaryVolumesSettings { enabled }            # WS_TVOL
      lightsailScanningSettings { enabled }                                # WS_LSAIL
      lambdaSettings { scannedVersionCount }                               # WS_LAMB (>0 = on)
    }
    azure {
      privateEndpointKeyVaults { enabled }                                 # WS_ADE1
      privateEndpointKeyVaultsWithFirewall { enabled }                     # WS_ADE2
    }
  }
  nod: nonOsDiskScanningSettings { enabled daysInterval }                  # WS_NONOS
  et:  eventTriggeredScanningSettings { enabled workloadScanningEnabled }  # WS_NRT
  sex: scannerExclusionSettings { tags { key value } }                     # WS_EXCL (count)

  # ===== C. Vulnerability Assessment (VS_*) ✅  (Linux-kernel mode ⚠️ see §7) =====
  vas: vulnerabilityAssessmentSettings {
    osPackageManagedCodeLibrariesVulnerabilitiesDetectionEnabled  # VS_OSPKG
    windowsManagedVulnerabilitiesDetectionEnabled                 # VS_WINB
    goStandardLibraryVulnerabilitiesEnabled                       # VS_GOSTD
    ignoreRedHatOpenshiftContainerLibraryVulnerabilities          # VS_RHOS
    pipInstalledPythonLibrariesVulnerabilitiesEnabled             # VS_PIP
    npmInstalledJavascriptLibrariesVulnerabilitiesEnabled         # VS_NPM
    codeLibraries {
      manifestFilesLifecycleStages  # VS_MANIF
      lockFilesLifecycleStages      # VS_LOCK
      artifactsLifecycleStages      # VS_ARTIF
      mavenScopes                   # VS_MAVEN
      npmScopes                     # VS_JSDEP
      gradleScopes                  # VS_GRADL
    }
    endOfLifeTechnologies { upcomingDetectionEnabled upcomingDetectionDays }  # VS_EOL
  }

  # ===== B. DSPM / Data Scanner config (DSS_*) — Azure PE ✅, per-source toggles ⚠️ (§7) =====
  dss: dataScannerSettings {
    azureStorageAccountConfig {
      privateEndpointGeneralConfig      { enabled }   # DSS_AZ1
      privateEndpointWithFirewallConfig { enabled }   # DSS_AZ2
    }
    azureCosmosDbConfig {
      privateEndpointGeneralConfig      { enabled }   # DSS_CDBAZ1
      privateEndpointWithFirewallConfig { enabled }   # DSS_CDBAZ2
    }
    # ⚠️ add per-source master toggles (buckets/dynamoDb/dataWarehouses/serverless/snowflake/
    #    bigQuery/virtualDrives/vmDisks/shadowData/AI sources) after introspecting DataScannerSettings.
  }

  # ===== D. Attack Surface (ASM) config ⚠️ — confirm root name via introspection (§7) =====
  asm: attackSurfaceScannerSettings {
    mode                              # Basic vs Advanced
    enabledSources                    # Recon / Runtime Sensor / Code / SaaS / API / Custom Targets
    detectionRules { name enabled }   # DAST / Default Creds / Misconfig / High-Profile / Vuln-Exploit / Early-Access
    riskSettings {
      vulnerability { enabled }  secret { enabled }
      secretValidation { enabled }  sensitiveData { enabled }
    }
    applicationEndpointExposurePolicy
  }

  # ===== F. Automation workflows (F_WF) ✅ =====
  wfOn:  automationWorkflows(filterBy: {enabled: true})  { totalCount }
  wfOff: automationWorkflows(filterBy: {enabled: false}) { totalCount }

  # ===== G. Service-catalog discovery rules (F_DR) ✅ =====
  drTotal: applicationServiceDiscoveryRules(first: 1) { totalCount }

  # ===== H. Container image lifecycle ladder — includes the CODE stage the MCP omits (CL_CODE) ✅ =====
  imgLifecycle: cloudResourcesGroupedByValues(
    filterBy: { type: {equals: ["CONTAINER_IMAGE"]} }
    groupBy:  { fields: [LIFECYCLE_STAGE] }
    first: 20
  ) { nodes { lifecycleStage analytics { resources { count } } } }

  # ===== I. Registry scan-source split (R_AUT / R_CON / R_CUS) ✅ (confirm enums if null) =====
  regAuto: containerRegistries(first: 1, filterBy: {scanningConfigurationType: [AUTOMATIC], hasDeployment: true}) { totalCount }
  regConn: containerRegistries(first: 1, filterBy: {scanningConfigurationType: [CONNECTOR], hasDeployment: true}) { totalCount }
  regCust: containerRegistries(first: 1, filterBy: {scanningConfigurationType: [CUSTOM],    hasDeployment: true}) { totalCount }

  # ===== K. Connectors WITH vs WITHOUT cloud events (CON_WE / CON_NE) — ✅ signal, ⚠️ root =====
  # Live-validated 2026-09-04: a connector HAS cloud events when its modules[] contains "EVENT_SCANNER"
  # (per-connector detail via the MCP get_connector: config.auditLogMonitorEnabled == true). The MCP
  # reaches connectors via list_deployments but caps at 20 nodes (totalCount can be in the hundreds) —
  # so aggregate here: page on endCursor and count nodes whose modules include EVENT_SCANNER.
  connectors(first: 100) {                          # ⚠️ confirm raw root name (connectors / deployments)
    totalCount
    nodes { id name modules }                       # CON_WE = modules includes "EVENT_SCANNER"; CON_NE = the rest
    pageInfo { hasNextPage endCursor }
  }

  # ===== L. Workloads with the Wiz runtime sensor (CON_WOS) — ✅ property live-validated 2026-09-04 =====
  sensorWorkloads: graphSearch(first: 1, projectId: "*", quick: true, query: {
    type: [VIRTUAL_MACHINE, CONTAINER, SERVERLESS], select: true,
    where: { deploymentCoverage_sensor_installed: {EQUALS: true} }   # ✅ confirmed property name
  }) { totalCount }
}
```

**Read it → tokens**

| Path | Token | Render |
|---|---|---|
| `ss.virtualMachineImages.enabled` | `WS_VM` | Enabled/Disabled |
| `ss.aws.snapshotReencryptionSettings.sharedCustomerManagedKeysArnPatterns.length` | `WS_CMK` | count |
| `ss.aws.workloadScanningUsingTemporaryVolumesSettings.enabled` | `WS_TVOL` | Enabled/Disabled |
| `ss.aws.lightsailScanningSettings.enabled` | `WS_LSAIL` | Enabled/Disabled |
| `ss.aws.lambdaSettings.scannedVersionCount > 0` | `WS_LAMB` | Enabled/Disabled |
| `ss.computeResourceGroupMemberScanSamplingEnabled` | `WS_CIGS` | Enabled/Disabled |
| `ss.azure.privateEndpointKeyVaults.enabled` / `…WithFirewall.enabled` | `WS_ADE1` / `WS_ADE2` | Enabled/Disabled |
| `et.enabled` | `WS_NRT` | Enabled/Disabled |
| `nod.enabled` (+ `daysInterval`) | `WS_NONOS` | `Enabled (Nd)` |
| `sex.tags.length` | `WS_EXCL` | `N tag-based exclusions` |
| each `vas.*` boolean | `VS_OSPKG/WINB/GOSTD/RHOS/PIP/NPM` | Enabled/Disabled |
| each `vas.codeLibraries.*` list | `VS_MANIF/LOCK/ARTIF/MAVEN/JSDEP/GRADL` | comma-joined or `None` |
| `vas.endOfLifeTechnologies.upcomingDetectionEnabled` (+days) | `VS_EOL` | `Enabled (Nd)` |
| `dss.azure*Config.*.enabled` | `DSS_AZ1/AZ2/CDBAZ1/CDBAZ2` | Enabled/Disabled |
| `asm.mode` / `asm.enabledSources` / `asm.detectionRules[]` / `asm.riskSettings.*` | ASM toggles | per template |
| `wfOn.totalCount` / `wfOff.totalCount` | `F_WF` | `"{on} on / {off} off"` |
| `drTotal.totalCount` | `F_DR` | count |
| `imgLifecycle.nodes[lifecycleStage=="CODE"].analytics.resources.count` | `CL_CODE` | count (other nodes → `CL_CLD/STR/RT/BLD/DEP`) |
| `regAuto/regConn/regCust.totalCount` | `R_AUT` / `R_CON` / `R_CUS` | count |
| connectors whose `modules` includes `"EVENT_SCANNER"` vs not | `CON_WE` / `CON_NE` | count (page + sum) |
| `sensorWorkloads.totalCount` | `CON_WOS` | count |

> **If a `⚠️` alias errors,** delete just that alias and re-run — the rest still return (GraphQL
> resolves aliases independently). Then introspect the failing type (§7) and re-add it. `automationWorkflows`
> can return `"Workflows are currently not supported"` on some tenants → `F_WF` stays N/A (gap F).

---

## Q2 — Posture trend & remediation  ✅

The slide-12 "are we improving / how fast do we fix" KPIs. Two date windows.

```graphql
query WhaGap2PostureTrend(
  $scoreStart: DateTime!   # 90d back
  $scoreEnd:   DateTime!   # now
  $mttrStart:  DateTime!   # 30d back (matches the tenant MTTR widget window)
  $mttrEnd:    DateTime!   # now
) {
  # 90-day Security-Score trend → s1d
  secScore: monitoredMetrics(first: 5, filterBy: {type: [SECURITY_SCORE], builtin: true}) {
    nodes { id name type dataPoints(startDate: $scoreStart, endDate: $scoreEnd, timeInterval: DAY) { time value } }
  }
  # Threat MTTR (mirrors the tenant widget) → MTTR_O/C/H ; MTTR_O = total / 86400 days
  mttr: issuesTrendV2(filterBy: {type: [THREAT_DETECTION]}, type: MTTR,
    startDate: $mttrStart, endDate: $mttrEnd, interval: DAY
  ) { total dataPoints { time totalValue criticalSeverityValue highSeverityValue } }
  # Average open issue age → AVG_AGEC / AVG_AGEH
  avgAge: issuesTrendV2(type: AVERAGE_ISSUE_AGE,
    startDate: $mttrStart, endDate: $mttrEnd, interval: ALL_RANGE, intervalType: RELATIVE
  ) { dataPoints { criticalSeverityValue highSeverityValue } }
}
```

**Variables** — RFC3339Nano, **`.000Z` required**. Paste as-is to run now; regenerate for the current
date with the §-top console snippet. Example anchored to 2026-09-04:
```json
{
  "scoreStart": "2026-06-06T00:00:00.000Z",
  "scoreEnd":   "2026-09-04T00:00:00.000Z",
  "mttrStart":  "2026-08-05T00:00:00.000Z",
  "mttrEnd":    "2026-09-04T00:00:00.000Z"
}
```

**Read it → tokens**

| Path | Token | Compute |
|---|---|---|
| `secScore.nodes[0].dataPoints[last].value − dataPoints[0].value` | `s1d` | signed delta, 1 dp (`+3.2`) |
| `mttr.total / 86400` (fallback `dataPoints[0].totalValue/86400`) | `MTTR_O` | days |
| `mttr.dataPoints[last].criticalSeverityValue / 86400` | `MTTR_C` | days |
| `mttr.dataPoints[last].highSeverityValue / 86400` | `MTTR_H` | days |
| `avgAge.dataPoints[0].criticalSeverityValue / 86400` | `AVG_AGEC` | days |
| `avgAge.dataPoints[0].highSeverityValue / 86400` | `AVG_AGEH` | days |

> ⚠️ Med/low threats auto-expire ~90d, so daily MTTR can pin near `7,776,000s` (= 90.0d);
> critical/high are the real signal.

---

## Q3 — Potential Integrations: totals + active  ✅

Slide 19 (gap J) — third-party tools detected but not connected to Wiz, tiered by prevalence, with
service-account counts. Two aliased `graphSearch` (totals + active subset). No variables.

```graphql
query WhaGap3PotentialIntegrations {
  totals: graphSearch(
    first: 500, projectId: "*", quick: false
    query: {
      select: true, type: [TECHNOLOGY]
      where: { deploymentModel: {EQUALS: ["Cloud service"]}, name: {DOES_NOT_CONTAIN: ["Wiz"]} }
      relationships: [{
        type: [{type: HAS_TECH, reverse: true}]
        with: {
          select: true, type: [SERVICE_ACCOUNT], aggregate: true
          where: {externalOwners: {IS_SET: true}}
          relationships: [{ type: [{type: CONTAINS, reverse: true}]
            with: { type: [SUBSCRIPTION, CLOUD_ORGANIZATION], where: {name: {DOES_NOT_START_WITH: ["Discovered"]}} } }]
        }
      }]
    }
  ) { nodes { aggregateCount entities { id name type properties } } }

  active: graphSearch(
    first: 500, projectId: "*", quick: false
    query: {
      select: true, type: [TECHNOLOGY]
      where: { deploymentModel: {EQUALS: ["Cloud service"]}, name: {DOES_NOT_CONTAIN: ["Wiz"]} }
      relationships: [{
        type: [{type: HAS_TECH, reverse: true}]
        with: {
          select: true, type: [SERVICE_ACCOUNT], aggregate: true
          where: { externalOwners: {IS_SET: true}, inactiveInLast90Days: {EQUALS: false} }
          relationships: [{ type: [{type: CONTAINS, reverse: true}]
            with: { type: [SUBSCRIPTION, CLOUD_ORGANIZATION], where: {name: {DOES_NOT_START_WITH: ["Discovered"]}} } }]
        }
      }]
    }
  ) { nodes { aggregateCount entities { id name type properties } } }
}
```

**Read it → tokens.** Per `nodes[]`: `entities[0].name` = tool, `aggregateCount` = service-account
count, `entities[0].properties.categories` → **Tier** (T1 = CNAPP/CSPM/CIEM/DSPM · T2 = Code/IaC/SAST/SCA
· T3 = CWPP/CDR/runtime). Roll up per tier → `PI_T1_COUNT/SA/AC/PA`, `PI_T2_*`, `PI_T3_*`, `PI_TOT_*`
and per-slot `PI_T{1,2,3}_{1..5}` (name/SA/AC/PA/category/last-seen from `properties.lastSeenAt`).
`active` gives the `_AC`/`_PA` subset. (Exact rollup logic: `api-delta-query.md §4a`.)

---

## Q4 — Potential Integrations: per-tech timeline  ✅  *(optional)*

Drives per-slot first/latest-seen (`_FA`/`_LA`) + NEW-in-90d (`_NC`/`_NF`). Paginated.

```graphql
query WhaGap4PiTimeline($after: String) {
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
          relationships: [{ type: [{type: CONTAINS, reverse: true}]
            with: { type: [SUBSCRIPTION, CLOUD_ORGANIZATION], where: {name: {DOES_NOT_START_WITH: ["Discovered"]}} } }]
        }
      }]
    }
  ) { nodes { entities { id name type properties } } pageInfo { hasNextPage endCursor } }
}
```
**Variables:** first page `{ "after": null }`; if `pageInfo.hasNextPage`, set `{ "after": "<endCursor>" }`
and re-run. **Read:** per-tech min/max SA `createdAt` → `_FA`/`_LA`; count created in last 90d → `_NC`/`_NF`.
Skip this and those fields render blank/`0` — tier counts + SA totals still render.

---

## Q5 — Feature-adoption users  ⚠️  *(optional, permission-gated)*

Distinct users of the **Browser Extension** (`F_BE`) and **Wiz MCP** (`F_WMCP`) — unique performers,
not seat count. Only path is the audit log — **live-validated 2026-09-04: requires `admin:audit` (or
`admin:all`); a `read:all` token is denied** (`UNAUTHORIZED`). Without that scope, both stay **N/A**.

```graphql
query WhaGap5AdoptionUsers($after: String, $since: DateTime!) {
  auditLogEntries(first: 500, after: $after, filterBy: { timestamp: {after: $since} }) {
    nodes { action user { id } serviceAccount { id } }
    pageInfo { hasNextPage endCursor }
  }
}
```
**Variables** (RFC3339Nano; 30-day window example):
```json
{ "after": null, "since": "2026-08-05T00:00:00.000Z" }
```
**Read:** page all entries; `F_BE` = distinct user IDs on browser-extension actions, `F_WMCP` = distinct
on Wiz-MCP actions. 403 or unclassifiable → both stay **N/A** (gap M).

---

## Manual / not-in-GraphQL (gaps N, O, P)  🖥️

| Token(s) | Where | Note |
|---|---|---|
| `L_SE` (sensor **units**) | Portal → **Settings → Licenses** | MCP/GraphQL expose sensor **groups**, not licensed units. |
| `ROADMAP_TRACKER` (slide 9) | Portal → **Roadmap Tracker** | API exposes *released* updates only. |
| Slide-4 "Cloud Advanced" %s | **Derive** from Q1 outputs | Advanced-ASM % from `asm.mode`; compute-scan/WizOS/SaaS % need scanner-mode + WizOS count + SaaS state. Any missing input → N/A. |

---

## Run instructions

1. Open the Sandbox for the tenant's region (`https://app.<region>.app.wiz.io/graphql-sandbox`).
2. Paste **Q1**, run — no variables. Fill every `WS_/VS_/DSS_/ASM/F_WF/F_DR/CL_CODE/R_*/CON_*` token
   still marked `Not available via MCP` from the response.
3. Paste **Q2** with the date variables (regenerate them via the console snippet), run, fill slide-12 tokens.
4. Paste **Q3** (+ **Q4** if you want the timeline), roll up into `PI_*`.
5. **Q5** only if you have `admin:audit`.
6. Re-render: `python3 render_deck.py --input-csv <csv> --format pptx --customer "<Name>"`. Unfilled
   cells stay **N/A** — the honest state for a genuine gap.

**Scope:** `read:all` covers Q1–Q4; Q5 needs `admin:audit`. No service account required.

---

## §7 Introspection (for ⚠️ fields)

When a `⚠️` alias returns `null` or a field error, introspect the type on this tenant's schema and
match the returned names into Q1:

```graphql
query Introspect { __type(name: "DataScannerSettings") { fields { name type { name kind ofType { name } } } } }
```
Swap the name for `ScannerSettings`, `VulnerabilityAssessmentSettings` (Linux-kernel field),
`AttackSurfaceScannerSettings` (ASM root), or `Query` (to find the connectors root + sensor property).

---

*Companion to `MCP_COVERAGE_GAPS.local.md` (gap inventory) and `docs/MCP_TOKEN_MAP.md` (MCP-reachable
tokens). Query text ported from the maintained service-account runbook
`agents/tam-cadence-coach/knowledge/api-delta-query.md` — ✅ paths are tenant-verified there, ⚠️ paths
need one introspection pass. No tenant data in this file.*
