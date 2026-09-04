# Wiz Tenant Health Assessment — MCP-Native

A **service-account-free** rebuild of the Wiz Tenant Health Assessment. All tenant data comes from
the **Wiz MCP server** (browser-OAuth) — there is **no Wiz service account, no API secret, and no
data-collection code** in this folder. The agent gathers metrics through the MCP, writes a CSV, and
this repo's offline renderer turns that CSV into the branded deck.

> Kept deliberately separate from the original service-account skill (`wiz-health-assessment-skill`)
> so the two never mix. This folder is fully self-contained.

## How it works
1. **Agent + MCP** collect the metrics per [`docs/MCP_TOKEN_MAP.md`](docs/MCP_TOKEN_MAP.md) and write
   a metrics CSV (see [`SKILL.md`](SKILL.md) for the runbook).
2. **`render_deck.py`** fills the PowerPoint template from that CSV — offline, pure Python standard
   library — nothing to install.

```bash
python3 render_deck.py --input-csv output/<metrics>.csv --format pptx --customer "Acme Corp"
```

## Requirements (minimal)
- **Wiz MCP** connected in your client (browser-OAuth). That's the only setup.
- **Python 3** — for the CSV and PPTX. The render pipeline is **pure standard library**; there is
  **nothing to `pip install`**.


## What's here
```
render_deck.py                # CSV -> PPTX (the only entry point)
SKILL.md                      # MCP-native runbook for the agent
docs/
  MCP_TOKEN_MAP.md            # authoritative token -> MCP-tool map (+ verified runtime corrections)
  MCP_ONLY_COVERAGE.md        # what the MCP can/can't populate, and why
  MCP_RUN_EXPECTATIONS.md     # measured runtime & token cost
  DECK_VARIABLE_REFERENCE.csv # the 440+ deck variables (catalog)
scripts/                      # pure-stdlib render pipeline (no service account, no GraphQL)
templates/                    # the PowerPoint master template
output/                       # sample MCP CSV + deck
```

## Coverage
~60–75% of deck variables populate from the MCP. Genuine gaps (marked **"Not available via MCP"**):
the data-scanner config block (`DSS_*`), most ASM/workload config toggles, integration activity
dates, and a few analytics KPIs. See [`docs/MCP_ONLY_COVERAGE.md`](docs/MCP_ONLY_COVERAGE.md).

## Security
Read-only. No credentials are ever requested or stored — the Wiz MCP handles auth via its own OAuth
session. This is the whole point of the MCP-native variant.
