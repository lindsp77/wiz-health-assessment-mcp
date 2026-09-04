# Wiz scan counts — accurate, reconciled (workload + data)

Count scans with **`execute_graph_query` against `SECURITY_TOOL_SCAN`**. **Never** use the scan
wrapper tools — see **Do not use** below. Same method for both scanners; only the *partitioning need*
differs (workload success caps; data usually doesn't).

## Base query
```
tool_name: execute_graph_query
parameters: {"query": {"type": ["SECURITY_TOOL_SCAN"], "select": true,
  "where": {"dataSource_name": {"EQUALS": ["<SCANNER>"]},
            "status": {"EQUALS": ["<STATUS>"]}}}, "first": 1}
```
Read `graphSearch.totalCount`. **Always check `graphSearch.maxCountReached`** — `true` means the
number is a **floor, not an answer**.

- `<SCANNER>`: `"Wiz Data Scanner"` (data security scans) or `"Wiz Workload Scanner"` (workload scans).
  Omit for both.
- `<STATUS>`: `ScanStatusSuccess`, `ScanStatusSkipped`, `ScanStatusError`. Omit for total.
- **`ScanStatusFailed` DOES NOT EXIST** — returns 0 silently. "Failed" in user language = `ScanStatusError`.
- `first: 1` keeps the payload small and does not affect the count. `select: true` is required
  (`select: ["id"]` errors).

## Always reconcile
`Success + Skipped + Error` **must equal** the unfiltered total for that scanner. Run all four. If they
do not sum, something is being silently excluded — find it before reporting.

## Handling the N cap
There is **no** server-side aggregation (`groupBy` is rejected). Partitioning and summing is the only
remedy. When a query returns `maxCountReached: true`, split on `scannedResourceType` and sum. Data
scans typically stay under the cap; **workload success typically does not.**

### Proving the partition is complete — the residual technique (use this, NOT sampling)
Sampling misses small types (one real type had **2 rows out of N**). Instead:
1. Count each known type with `scannedResourceType: {EQUALS: ["<type>"]}`.
2. Query the **residual**: same filter with `scannedResourceType: {NOT_EQUALS: [<every known type>]}`.
3. If residual `totalCount > 0`, read `scannedResourceType` off the **first returned row**, add it, repeat.
4. Stop when residual = 0 — that is **proof of exhaustiveness**, not an estimate.
5. Sum the per-type counts.

This found 5 types in no documentation and unguessable: `Container`, `Endpoint`, `RepositoryBranch`,
`Ide`, `Workstation` — together **N% of workload scans**.

## `scannedResourceType` values (prefix every value with `SecurityToolScanScannedResourceType`)
`ContainerImage`, `Container`, `Bucket`, `Endpoint`, `RepositoryBranch`, `OSDisk`, `NonOSDisk`,
`Serverless`, `VirtualMachineImage`, `VirtualWorkspace`, `Database`, `DBServer`, `AiDataset`, `Ide`,
`Workstation`.
Traps: VM scans file under **OSDisk** (`VirtualMachine`=0); data disks under **NonOSDisk** (`Volume`=0);
**DBServer** has a capital DB; **RepositoryBranch**, not `Repository`. **Always re-run the residual
check on a new tenant — this list is not guaranteed complete elsewhere.**

## If a single type is still capped
Split further by subscription (high cardinality, scales with tenant). Enumerate accounts with
`list_subscriptions`, then scope each via a `SCANNED`→`CLOUD_RESOURCE` relationship filtered by
`subscriptionExternalId`. **Budget rule:** if the plan would exceed ~N calls, stop — either use
`resourceScanResultsGroupedByValues` (server-side grouping, one call, via the Wiz GraphQL API, **not**
the MCP) or report the floor as "≥N" with the reason. Ask what the number is for: a coverage %
needs precision; "are we scanning a lot" does not.

## The null-partition trap
A partition key with `null` values silently drops rows from every branch (confirmed: `dataSource_name`
absent on Cloud-API-scan rows carrying `dataSourceId: N`; `statusDetails` absent entirely on some
rows). The residual query catches missing *enum values* but **NOT null-valued rows** — so still
reconcile the partitioned sum against a known parent wherever one is visible.

## Worked example (reference tenant, Sep 2026 — shows the method, not expected values)
- **Data scans** — all four uncapped, no partitioning: N success + N skipped + N error = N ✓
- **Workload scans** — success capped, partitioned across N types, residual driven to 0:
  **N success + N skipped + N error = N total**. Unpartitioned success reported N /
  `maxCountReached: true` — a **N undercount**. Success by type: ContainerImage N · Container
  N · Bucket 1914 · Endpoint N · RepositoryBranch N · OSDisk N · Serverless N ·
  VirtualMachineImage N · Ide N · Database N · VirtualWorkspace N · DBServer N · NonOSDisk N ·
  Workstation 2.

## Breaking down by reason
Partition by `scannedResourceType`, sample each (`"first": N`, overflows to a file — use `jq`, never
read whole):
```
jq -r '[.graphSearch.nodes[].entities[].properties.statusDetails] | group_by(.) | map({msg:.[0], n:length}) | sort_by(-.n) | .[] | "\(.n)\t\(.msg)"' <path>
```
Then exact-count each message with `statusDetails: {EQUALS: [...]}`, aggregate identifier-bearing
families with `CONTAINS` on a stable prefix, reconcile the per-message sum to the partition total. Some
rows have **no** `statusDetails` property — they are real rows and `NOT_EQUALS` drops them.

## Scans vs resources — state which you answered
- "How many **scans**" → root on `SECURITY_TOOL_SCAN`.
- "How many **resources** were scanned" → root on `CLOUD_RESOURCE` with a reverse `SCANNED` relationship.
- Measured: N data scans vs N data-scanned resources. Both correct, different questions — the
  most common cause of "your number doesn't match mine".

## Current state vs event history
`SECURITY_TOOL_SCAN` nodes are the **latest scan per resource** (overwritten each run) — NOT a
historical log. **Settings → Workload Scan Log** is an event log over time. Never present the two in
one table. ⚠️ Note `Endpoint` scans and `RepositoryBranch` scans are filed under the Workload Scanner
but are external-exposure and VCS-branch scans — so `dataSource_name: Wiz Workload Scanner` is a
different boundary than the scan-log page's `dataScan: false`; expect a gap when comparing.

## Portal equivalents
These same query objects paste directly into Wiz Advanced Search (`app.wiz.io/explorer/graph`). The
portal rejects `dataSourceId` as unsupported — use `dataSource_name`. `dataSourceId` (N workload / N
data) still works via the API and is slightly broader (covers rows with no `dataSource_name`).

## Do not use
- **`summarize_scan_failures_by_account_region`** — claims workload failures, returns workload AND data
  merged; `filterBy.status` hardcoded to failures, no parameter to widen.
- **`get_data_scan_results`** — returns workload rows alongside data scans and only a small subset
  (N of N).
- **`list_workload_scan_failures`** — reports a capped `totalCount: N`.
> General rule: tool names in this MCP assert scopes their parameters do not enforce. Verify returned
> rows against the claimed scope before reporting any wrapper's number.

## Reporting
State the **scanner**, **status**, **root entity**, and whether the count was **capped or partitioned**.
If a number cannot be made accurate, say so and name the operation that can.
