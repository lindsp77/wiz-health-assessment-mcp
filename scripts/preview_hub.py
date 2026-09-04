"""
Preview Hub Transformer for QBR Deck Builder.

Ports the n8n Transform Preview Hub Deck node to Python.
Categorizes Wiz Preview & Migration Hub items into public/private,
billable/non-billable tiers, and formats bullet lists for slides.
"""

from typing import Any, Dict, List, Tuple


TIERS = ["ADVANCED", "DEFEND", "SENSOR", "CODE", "ESSENTIAL", "PLATFORM"]
PORTAL_BASE = "https://app.wiz.io"


def is_billable(it: Dict[str, Any]) -> bool:
    return it.get("billable") is True


def is_private(it: Dict[str, Any]) -> bool:
    return it.get("private") is True


def is_migration(it: Dict[str, Any]) -> bool:
    t = str(it.get("featureType") or it.get("type") or "").upper()
    return t in ("MIGRATION", "DEPRECATION")


def clean_name(n: Any) -> str:
    return " ".join(str(n or "Unknown").split()).strip()


def primary_tier(it: Dict[str, Any]) -> str:
    cats = it.get("licenseCategories") or []
    for p in TIERS:
        if p in cats:
            return p
    return "PLATFORM"


def link_for(it: Dict[str, Any]) -> str:
    d = str(it.get("docsUrl") or "").strip()
    if d:
        return d
    cta = it.get("cta") or {}
    rel = str(cta.get("relativeUrl") or "").strip()
    if rel:
        return PORTAL_BASE + ("" if rel.startswith("/") else "/") + rel
    return ""


def bullets(arr: List[str]) -> str:
    sorted_arr = sorted(arr, key=lambda s: s.lower())
    return "\n".join(f"• {n}" for n in sorted_arr)


def transform_preview_hub(items: List[Dict[str, Any]]) -> Tuple[Dict[str, str], List[Dict[str, str]]]:
    """
    Transform raw Preview & Migration Hub items into deck variables and links.
    """
    tier_lists = {}
    priv_bill = []
    priv_non_bill = []
    link_list = []
    seen_links = set()

    for it in items:
        if is_migration(it):
            continue
        name = clean_name(it.get("title") or it.get("name"))
        cat = primary_tier(it)
        bill = is_billable(it)
        url = link_for(it)

        if url and name not in seen_links:
            link_list.append({"name": name, "url": url})
            seen_links.add(name)

        if is_private(it):
            if bill:
                priv_bill.append(name)
            else:
                priv_non_bill.append(name)
            continue

        key = f"{'B' if bill else 'N'}|{cat}"
        tier_lists.setdefault(key, []).append(name)

    pub_bill_tot = 0
    pub_non_bill_tot = 0
    vars_out = {}
    pub_non_bill_all = []

    for cat in TIERS:
        b = tier_lists.get(f"B|{cat}", [])
        n = tier_lists.get(f"N|{cat}", [])
        vars_out[f"BILLABLE_{cat}"] = bullets(b)
        vars_out[f"NON_BILLABLE_{cat}"] = bullets(n)
        pub_bill_tot += len(b)
        pub_non_bill_tot += len(n)
        pub_non_bill_all.extend(n)

    vars_out["BILLABLE_TOTAL"] = str(pub_bill_tot)
    vars_out["NON_BILLABLE_TOTAL"] = str(pub_non_bill_tot)
    vars_out["ALL_NON_BILLABLE_PREVIEW"] = bullets(pub_non_bill_all)
    vars_out["PRIVATE_BILLABLE"] = bullets(priv_bill)
    vars_out["PRIVATE_NON_BILLABLE"] = bullets(priv_non_bill)
    vars_out["PRIVATE_BILLABLE_TOTAL"] = str(len(priv_bill))
    vars_out["PRIVATE_NON_BILLABLE_TOTAL"] = str(len(priv_non_bill))
    vars_out["PRIVATE_TOTAL"] = str(len(priv_bill) + len(priv_non_bill))
    vars_out["PUBLIC_TOTAL"] = str(pub_bill_tot + pub_non_bill_tot)
    vars_out["PREVIEW_HUB_TOTAL"] = str(pub_bill_tot + pub_non_bill_tot + len(priv_bill) + len(priv_non_bill))

    return vars_out, link_list


def format_tracked_roadmap_items(nodes: List[Dict[str, Any]], limit: int = 20) -> str:
    """
    Format tracked roadmap items into a bulleted list for Slide 18 (Roadmap Tracker).
    Option A format: • Title [Ticket] — Status (Target)
    """
    status_map = {
        "PLANNED": "Planned",
        "IN_DEVELOPMENT": "In Development",
        "PRIVATE_PREVIEW": "Private Preview",
        "PUBLIC_PREVIEW": "Public Preview",
        "GENERAL_AVAILABILITY": "GA"
    }
    lines = []
    for n in (nodes or [])[:limit]:
        title = clean_name(n.get("title") or n.get("name"))
        if not title or title == "Unknown":
            continue
        ticket_id = (n.get("ticketId") or "").strip()
        ticket_str = f" [{ticket_id}]" if ticket_id else ""

        raw_status = n.get("developmentStatus")
        status_str = status_map.get(raw_status, raw_status.replace("_", " ").title() if raw_status else "")

        prd = n.get("plannedReleaseDate") or {}
        q = prd.get("quarter")
        y = prd.get("year")
        target_str = f" (Q{q} {y})" if (q and y) else (f" ({y})" if y else "")

        if status_str:
            line = f"• {title}{ticket_str} — {status_str}{target_str}"
        else:
            line = f"• {title}{ticket_str}"
        lines.append(line)
    return "\n".join(lines)
