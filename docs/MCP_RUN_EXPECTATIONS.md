# MCP-Only Run — Expectations, Runtime & Token Cost

**Applies to:** `skills/wiz-health-assessment-mcp` (the MCP-only, CSV-output path).
**Purpose:** set operator expectations for how long a run takes and roughly how many tokens it burns,
and why — so a customer isn't surprised when it runs for many minutes.

> Numbers in the **Measured** table below come from real runs (not estimates). The first row is the
> 2026-09-03 validation run against a large internal tenant. Add a row after each subsequent run.

---

## Why it takes a while (structural)

The Wiz MCP has **no batch mode** — every metric is a separate `execute` round-trip
(agent → remote Wiz MCP → GraphQL → tenant → back). The runbook is ~40+ such calls, issued
**sequentially**, and several deck sections need *many filtered calls each* because coverage counts
are obtained by calling once per filter and reading `totalCount`:

| Section | Calls | Why |
|---|---|---|
| Kubernetes ladder | ~10 | one call per deployment status (connector/admission/sensor/audit-log Installed vs NotInstalled) + internet-exposed + per-flavor |
| Subscriptions / connectors | ~6 | one call per cloud provider + per connection status |
| System-health breakdown | ~9 | one call per deployment type (cloud/k8s/registry/VCS/outpost/broker/integration) |
| Issues (posture + top controls) | ~8 | per severity × status, plus grouped-by-source-rule (crit + high) |
| Endpoints / Red Agent | ~4 | per protocol group + AI-powered findings |
| Everything else (score, AI, DSPM, licenses, previews, etc.) | ~12 | mostly one call each |

**Total ≈ 45–50 sequential MCP calls.** Wall-clock is dominated by that call count × per-call
latency, not by local compute.

## What makes a given tenant slower or faster

- **Tenant size.** More cloud accounts, clusters, issues, and datastores mean each aggregate query
  does more work server-side. (The 2026-09-03 tenant had 688 cloud accounts, 213 clusters,
  1,356 open system-health issues.)
- **Enabled Preview Hub features / integrations.** Larger result sets on those list calls.
- **MCP/GraphQL latency & throttling** at the time of the run.
- **Model doing the collection.** A cheaper model (Sonnet) is fine here — the work is
  call-a-tool-then-map, not deep reasoning — and keeps token cost down.

## Token cost — what drives it

Context grows with the **size of the MCP responses** the agent reads, not the number of tokens in
the final CSV. The heavy responses are the list-style calls (subscriptions, clusters, datastores,
preview hub, cloud events). Using `first:1` and reading only the count field (as the runbook
instructs) keeps most calls small; the unavoidable cost is the ~45 responses plus reading the
440-row catalog and writing the 440-row CSV.

---

## Measured (fill after each run)

| Date | Tenant profile | MCP calls | Duration | Agent tokens | Model | Coverage (populated / 440) |
|---|---|---|---|---|---|---|
| 2026-09-03 | Large internal (~600 accts, 213 clusters, 1,356 SHIs) | 164 tool calls | ~15.1 min (905 s) | ~460k | Sonnet | 232 / 440 (~53%) |

**Reading the first run:** 164 calls is *higher* than the ~45-call runbook because this was a
validation run — ~11 tool-schema deviations forced retries, and top-control name resolution added
one `list_controls` lookup per source rule. With the corrections now folded into
`MCP_TOKEN_MAP.md`, a clean production run should land closer to **~55–65 calls** and proportionally
fewer tokens/less time. **Budget rule of thumb: ~10–20 min and ~0.3–0.5M tokens on a large tenant**;
smaller tenants are faster. The ~53% coverage matches the documented MCP ceiling (the remaining ~47%
is the config-toggle blocks + per-status scan splits + a few analytics/adoption gaps).

---

## Operator guidance / expectation-setting for customers

- **Tell the customer up front it can take several minutes** (single-digit to low-double-digit),
  longer on large tenants — it is making dozens of live queries, not one.
- It is **read-only** and safe to leave running; there is no partial-write risk (the CSV is written
  once at the end).
- If a run must be faster, the **production optimization** is to fetch list families **once** and
  aggregate client-side (e.g., pull clusters/subscriptions in a couple of paged calls and count by
  attribute locally) instead of one filtered `totalCount` call per bucket — this can cut the ~45
  calls to ~20. Validate correctness first (that is what the 2026-09-03 run is for), then optimize.
