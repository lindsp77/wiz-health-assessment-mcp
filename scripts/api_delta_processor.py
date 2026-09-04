"""
API Delta Processor and Deck Variable Generator for QBR Deck Builder.

Ports Vercel app processRawApiDelta and n8n Prep Deck 2 node logic to Python.
Parses raw API Delta JSON blocks, merges with BigQuery metrics, applies formatting
and Best Practice rules, and generates Google Slides batchUpdate replaceAllText requests.
"""

import json
import math
import re
import collections
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Set


FMT_BIG_VARS = {
    "CE_1", "CE_2", "CE_3", "CE_4", "CE_5", "CE_6", "CE_7", "CE_8", "CE_9", "CE_10", "CE_11", "CE_12", "CE_13"
}

FMT_THOU_VARS = set()

RECS = {
    "WS_NONOS": "Enabled", "WS_VM": "Enabled", "WS_CMK": ">0", "WS_SNAP": None,
    "WS_TVOL": "Enabled", "WS_LSAIL": "Enabled", "WS_LAMB": "Enabled", "WS_TAGS": None,
    "WS_EXCL": None, "WS_CIGS": None, "WS_ADE1": "Enabled", "WS_ADE2": "Enabled",
    "WS_NRT": "Enabled", "WS_NRTW": "Enabled", "WS_AFIM": "Enabled",
    "ASM_ON": "Enabled", "ASM_MODE": "Advanced", "ASM_MISC": "Enabled", "ASM_CRED": "Enabled",
    "ASM_VULN": "Enabled", "ASM_DATA": "Enabled", "ASM_SEC": "Enabled", "ASM_DAST": "Enabled",
    "ASM_VEXP": "Enabled", "ASM_HPT": None, "ASM_EAR": None, "ASM_API": "Enabled", "ASM_CUST": None,
    "ASM_EXPL": "Moderate", "ASM_CODE": "Enabled", "ASM_RS": "Enabled",
    "ASM_RECON": "Enabled", "ASM_SAAS": "Enabled", "ASM_SV": "Enabled",
    "VS_LVULN": None, "VS_OSPKG": None, "VS_WINB": None, "VS_GOSTD": None, "VS_EXCL": None, "VS_RHOS": None,
    "VS_MANIF": "Enabled", "VS_LOCK": "Enabled", "VS_ARTIF": "Enabled", "VS_EOL": "Enabled",
    "VS_MAVEN": None, "VS_JSDEP": None, "VS_GRADL": None,
    "DSS_ON": "Enabled", "DSS_BUCK": "Enabled (Public & Private)", "DSS_AZ1": "Enabled", "DSS_AZ2": "Enabled",
    "DSS_VDRV": "Enabled", "DSS_PAAS": "Enabled", "DSS_DW": "Enabled", "DSS_BQ": "Enabled",
    "DSS_DDB": "Enabled", "DSS_SNOW": "Enabled", "DSS_IAAS": "Enabled", "DSS_VMD": "Enabled",
    "DSS_SLS": "Enabled", "DSS_AIV": None, "DSS_AIAO": None, "DSS_AIOA": None,
    "DSS_SHAD": "Enabled", "DSS_CID": "Enabled", "DSS_CDBAZ1": "Enabled", "DSS_CDBAZ2": "Enabled"
}

BP = {"aligned": "✅", "gap": "❌", "neutral": "N/A"}


def fmt_big(n: Any) -> str:
    if n is None or n == "":
        return "N/A"
    s = str(n).strip()
    if re.match(r"^[\d.,]+\s*[KMB]$", s, re.IGNORECASE):
        return s
    try:
        num = float(s)
    except ValueError:
        return s
    if num >= 1e9:
        return f"{(num / 1e9):.1f}B"
    if num >= 1e6:
        return f"{(num / 1e6):.1f}M"
    if num >= 1e3:
        return f"{(num / 1e3):.1f}K"
    return str(round(num))


def fmt_thou(n: Any) -> str:
    if n is None or n == "":
        return "N/A"
    s = str(n).strip()
    if re.match(r"^\d{1,3}(,\d{3})+$", s):
        return s
    try:
        has_plus = s.startswith("+")
        num = float(s.lstrip("+").replace(",", ""))
        prefix = "+" if has_plus and num > 0 else ""
        if num.is_integer():
            return f"{prefix}{int(num):,}"
        return f"{prefix}{num:,.1f}"
    except (ValueError, TypeError):
        return s


def apply_fmt(variable: str, value: Any) -> str:
    if not value and value != 0:
        return ""
    if re.match(r"^(CE|RC)_\d+$", variable) and str(value).strip() in ("0", "0.0"):
        return ""
    if variable in FMT_BIG_VARS:
        return fmt_big(value)
    return fmt_thou(value)


def eval_config(cur: str, rec: Optional[str]) -> str:
    if rec is None:
        return "neutral"
    c = (cur or "").strip().lower()
    # MCP-only mode: a scanner toggle the Wiz MCP cannot read is filled with a
    # "Not available via MCP" sentinel. Render its recommendation as N/A — never
    # aligned/gap — otherwise the non-empty sentinel string would score as "aligned".
    if "not available" in c or "not assessed" in c:
        return "neutral"
    r = rec.strip()
    rl = r.lower()
    if r.startswith(">"):
        try:
            th = float(r[1:])
            v = float(c)
            return "aligned" if v > th else "gap"
        except ValueError:
            return "gap"
    if rl == "enabled":
        return "gap" if c in ("disabled", "n/a", "", "0", "none") else "aligned"
    if rl == "disabled":
        return "aligned" if c == "disabled" else "gap"
    rm = rl[:-1] if rl.endswith(")") else rl
    return "aligned" if (c.startswith(rm) or c == rl) else "gap"


def split_json_blocks(text: str) -> List[Dict[str, Any]]:
    """Split multiple concatenated JSON objects in text into a list of parsed dicts."""
    blocks = []
    depth = 0
    start = -1
    in_str = False
    esc = False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            continue
        if ch == '{':
            if depth == 0:
                start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and start != -1:
                try:
                    blocks.append(json.loads(text[start : i + 1]))
                except Exception:
                    pass
                start = -1
    return blocks


def classify_blocks(blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Classify JSON blocks into Q1..Q5, QShi, etc."""
    q1 = None
    q2 = None
    q3 = None
    q4c = None
    q_shi = None
    q_ai = None
    q5 = None
    q4_aggregate = []

    for block in blocks:
        d = block.get("data") if isinstance(block, dict) else None
        if not d:
            continue

        if d.get("systemHealthIssues") is not None:
            q_shi = d
        if (d.get("aiSecFindings") is not None or d.get("aiMisconfigFindings") is not None
                or d.get("inventoryFindingsCount") is not None or d.get("aiSecurityFindingsCount") is not None
                or d.get("cloudConfigFindingsCount") is not None or d.get("aiModels") is not None):
            if q_ai is None:
                q_ai = {}
            q_ai.update(d)
        if (d.get("ds_total") is not None or d.get("webCrawlerApiEndpoints") is not None
                or d.get("webDastAttackerFindings") is not None or d.get("shi_open_crit") is not None
                or d.get("integrationsList") is not None or d.get("customFrameworksAll") is not None):
            # Merge (don't overwrite) so Q5 data split across multiple blocks accumulates.
            if q5 is None:
                q5 = {}
            q5.update(d)

        if d.get("disc_all") is not None or d.get("discoveredResources") is not None or d.get("workloadScans") is not None or d.get("imgLifecycle") is not None:
            q1 = d
        elif d.get("rcIssues") is not None or (d.get("mttr") is not None and d.get("rcIssues") is not None):
            q2 = d
        elif d.get("uTot") is not None or d.get("champItems") is not None or d.get("billableWorkloadTrendV2") is not None or d.get("outposts") is not None or d.get("sensors") is not None or d.get("kc_wc") is not None or d.get("kg_na") is not None or d.get("criticalControls") is not None or d.get("highControls") is not None:
            if q3 is None:
                q3 = {}
            q3.update(d)
        elif d.get("q4a_totals") and d.get("q4b_active"):
            q4_aggregate.append({"graphSearch": d["q4a_totals"]})
            q4_aggregate.append({"graphSearch": d["q4b_active"]})
        elif d.get("graphSearch") and d["graphSearch"].get("nodes"):
            nodes = d["graphSearch"]["nodes"]
            first = nodes[0] if len(nodes) > 0 else {}
            if first.get("entities") and len(first["entities"]) > 1:
                if not q4c:
                    q4c = d
                else:
                    q4c["graphSearch"]["nodes"].extend(nodes)
            else:
                q4_aggregate.append(d)

    def total_count(resp):
        nodes = ((resp.get("graphSearch") or {}).get("nodes")) or []
        return sum(n.get("aggregateCount", 0) for n in nodes)

    q4_aggregate.sort(key=total_count, reverse=True)

    return {
        "q1": q1,
        "q2": q2,
        "q3": q3,
        "q4a": q4_aggregate[0] if len(q4_aggregate) > 0 else None,
        "q4b": q4_aggregate[1] if len(q4_aggregate) > 1 else None,
        "q4c": q4c,
        "q5": q5,
        "qShi": q_shi,
        "qAi": q_ai,
    }


def run_post_process(c: Dict[str, Any]) -> Dict[str, str]:
    """Extract flat variables from classified query blocks."""
    q1 = c.get("q1") or {}
    q2 = c.get("q2") or {}
    q3 = c.get("q3") or {}
    q4a = c.get("q4a") or {}
    q4b = c.get("q4b") or {}
    q5 = c.get("q5") or {}
    q_shi = c.get("qShi") or {}
    q_ai = c.get("qAi") or {}
    q4c_blocks = [c["q4c"]] if c.get("q4c") else []
    out = {}

    def on_off(b):
        return "Enabled" if b is True else "Disabled" if b is False else "N/A"

    def fmt_r(n):
        if n is None:
            return "N/A"
        try:
            num = float(n)
        except (ValueError, TypeError):
            return str(n)
        if num.is_integer():
            return f"{int(num):,}"
        return f"{num:,.1f}"

    def sec2days(v):
        if v is None:
            return "N/A"
        try:
            return str(round(float(v) / 86400.0))
        except (ValueError, TypeError):
            return "N/A"

    def fmt_dmy(iso):
        if not iso or not isinstance(iso, str) or len(iso) < 10:
            return ""
        return f"{iso[5:7]}-{iso[8:10]}-{iso[2:4]}"

    reg_label = {
        "ECR": "ECR", "GAR": "GAR", "GCR": "GCR", "ACR": "ACR",
        "DOCKER_HUB": "Docker Hub", "JFROG_ARTIFACTORY": "JFrog",
        "JFROG": "JFrog", "NEXUS": "Nexus", "GHCR": "GHCR"
    }
    mod_lbl = {
        "AI_SECURITY": "AI Security", "ATTACK_SURFACE_MANAGEMENT": "Attack Surface Mgmt",
        "CIEM": "CIEM", "CLOUD_COST": "Cloud Cost", "CLOUD_DETECTION_AND_RESPONSE": "CDR",
        "COMPLIANCE": "Compliance", "CONTAINER_AND_KUBERNETES_SECURITY": "Container & K8s",
        "CSPM_AND_COMPLIANCE": "CSPM", "DATA_SECURITY": "Data Security",
        "GETTING_STARTED": "Getting Started", "SECURE_CLOUD_DEVELOPMENT": "Secure Cloud Dev",
        "SECURE_USE_OF_SECRETS": "Secrets Mgmt", "VULNERABILITY_MANAGEMENT": "Vuln Mgmt",
        "ZERO_CRITICAL": "Zero Critical"
    }
    cc_var = {
        "GETTING_STARTED": "CCO_GS", "DATA_SECURITY": "CCO_DS", "COMPLIANCE": "CCO_C",
        "CSPM_AND_COMPLIANCE": "CCO_SCC", "ZERO_CRITICAL": "CCO_ZC",
        "ATTACK_SURFACE_MANAGEMENT": "CCO_ASM", "VULNERABILITY_MANAGEMENT": "CCO_VM",
        "AI_SECURITY": "CCO_AIS", "SECURE_CLOUD_DEVELOPMENT": "CCO_SCD",
        "CONTAINER_AND_KUBERNETES_SECURITY": "CCO_KS", "CIEM": "CCO_CIEM",
        "CLOUD_DETECTION_AND_RESPONSE": "CCO_TDR", "SECURE_USE_OF_SECRETS": "CCO_SS",
        "CLOUD_COST": "CCO_CC"
    }

    tier_cats = {
        "Tier 1": {"cspm (cloud security posture management)", "cnapp (cloud-native application protection platform)", "ciem (cloud infrastructure entitlement management)", "dspm (data security posture management)", "data access management", "attack surface management"},
        "Tier 2 (Code)": {"infrastructure as code analysis", "sast (static application security testing)", "dast (dynamic application security testing)", "sca (software composition analysis)", "code secret scanner", "integrated development environment (ide) tools", "code security"},
        "Tier 3 (Sensor)": {"cwpp (cloud workload protection platform)", "container runtime security", "runtime security", "threat detection and response", "container image scanners", "container security"},
    }

    def classify_tiers(cats_str):
        lst = [s.strip().lower() for s in (cats_str or "").split(",") if s.strip()]
        hits = []
        for t in ["Tier 1", "Tier 2 (Code)", "Tier 3 (Sensor)"]:
            if any(c in tier_cats[t] for c in lst):
                hits.append(t)
        return hits if hits else ["Other"]

    def is_uuid(s):
        if not s:
            return True
        return bool(re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-", str(s), re.IGNORECASE))

    # --- Q1 ---
    out["DISC"] = fmt_r((q1.get("disc_all") or {}).get("totalCount", 0))
    out["DISC_IMG"] = fmt_r((q1.get("disc_img") or {}).get("totalCount", 0))
    out["DISC_K8S"] = fmt_r((q1.get("disc_k8s") or {}).get("totalCount", 0))
    out["DISC_REPO"] = fmt_r((q1.get("disc_repo") or {}).get("totalCount", 0))
    out["DISC_REG"] = fmt_r((q1.get("disc_reg") or {}).get("totalCount", 0))
    out["U_RES"] = fmt_r((q1.get("discoveredResources") or {}).get("totalCount") or (q1.get("disc_all") or {}).get("totalCount", 0))
    out["KG_IA"] = str((q1.get("kg_ia") or {}).get("totalCount", 0))
    out["KC_AL"] = str((q1.get("kc_al") or {}).get("totalCount", 0))

    # Workload Scans & Coverage
    ws_nodes = (q1.get("workloadScans") or {}).get("nodes") or []
    if ws_nodes:
        ws_counts = { (n.get("values") or {}).get("status"): n.get("scanCount", 0) for n in ws_nodes }
        ws_success = ws_counts.get("SUCCESS", 0)
        ws_failed = ws_counts.get("FAILED", 0)
        ws_skipped = ws_counts.get("SKIPPED", 0)
        ws_total = ws_success + ws_failed + ws_skipped
        out["WS_T"] = fmt_r(ws_total)
        out["WS_F"] = fmt_r(ws_failed)
        out["WS_SK"] = fmt_r(ws_skipped)
        ws_ratio = q1.get("workloadScanRatio") or {}
        if ws_ratio.get("totalResourceCount"):
            s_cnt = ws_ratio.get("successResourceCount", 0)
            t_cnt = ws_ratio.get("totalResourceCount", 1)
            out["WS_P"] = f"{int(math.floor(s_cnt / t_cnt * 100))}%"
        elif ws_total > 0:
            out["WS_P"] = f"{int(math.floor((ws_total - ws_failed - ws_skipped) / ws_total * 100))}%"

    # Application Endpoints (ASM)
    ae_h = (q1.get("appEndpointsHttp") or {}).get("totalCount")
    ae_nh = (q1.get("appEndpointsNonHttp") or {}).get("totalCount")
    if ae_h is not None:
        out["AE_HTTP"] = fmt_r(ae_h)
    if ae_nh is not None:
        out["AE_NHTTP"] = fmt_r(ae_nh)
    if ae_h is not None and ae_nh is not None:
        ae_wtot = round((ae_h / 25.0) + (ae_nh / 50.0))
        out["AE_TOT"] = fmt_r(ae_wtot)
        out["AE_WTOT"] = fmt_r(ae_wtot)
    elif (q1.get("appEndpointsAll") or {}).get("totalCount") is not None:
        ae_all = (q1.get("appEndpointsAll") or {}).get("totalCount", 0)
        out["AE_TOT"] = fmt_r(ae_all)

    lc = {}
    for n in ((q1.get("imgLifecycle") or {}).get("nodes") or []):
        stg = n.get("lifecycleStage")
        cnt = ((n.get("analytics") or {}).get("resources") or {}).get("count", 0)
        lc[stg] = cnt

    out["CL_CLD"] = fmt_r(lc.get("CLOUD", 0))
    out["CL_STR"] = fmt_r(lc.get("STORE", 0))
    out["CL_RT"] = fmt_r(lc.get("RUNTIME", 0))
    out["CL_CODE"] = fmt_r(lc.get("CODE", 0))
    out["CL_BLD"] = fmt_r(lc.get("BUILD", 0))
    out["CL_DEP"] = fmt_r(lc.get("DEPLOY", 0))
    imgs_total = sum(lc.values())
    ti_unique = (q1.get("totalContainerImages") or q3.get("totalContainerImages") or q1.get("containerImages") or q3.get("containerImages") or {}).get("totalCount")
    if ti_unique is not None:
        out["TI"] = fmt_r(ti_unique)
        out["IMGS"] = fmt_r(ti_unique)
    elif imgs_total > 0:
        out["IMGS"] = fmt_r(imgs_total)
        out["TI"] = fmt_r(imgs_total)

    reg_counts = {}
    r_nodes = ((q1.get("registries") or q3.get("registries") or {}).get("nodes") or [])
    for n in r_nodes:
        lbl = reg_label.get(n.get("type"), "Other")
        reg_counts[lbl] = reg_counts.get(lbl, 0) + 1
    sorted_regs = sorted(reg_counts.items(), key=lambda x: x[1], reverse=True)
    for i in range(6):
        out[f"R_{i+1}"] = sorted_regs[i][0] if i < len(sorted_regs) else ""
        out[f"RC_{i+1}"] = str(sorted_regs[i][1]) if i < len(sorted_regs) else ""

    r_con = sum(1 for r in r_nodes if r.get("scanningConfigurationType") == "CONNECTOR")
    r_aut = sum(1 for r in r_nodes if r.get("scanningConfigurationType") == "GLOBAL")
    r_cus = sum(1 for r in r_nodes if r.get("scanningConfigurationType") == "CUSTOM")

    out["R_CON"] = str(r_con)
    out["R_AUT"] = str(r_aut)
    out["R_CUS"] = str(r_cus if r_cus > 0 else (q1.get("customRegistries") or {}).get("totalCount", 0))

    ss = q1.get("ss") or {}
    nod = q1.get("nod") or {}
    et = q1.get("et") or {}
    srt = q1.get("srt") or {}
    sex = q1.get("sex") or {}
    fim = q1.get("fim") or {}
    vas = q1.get("vas") or {}
    dss = q1.get("dss") or {}

    out["WS_NONOS"] = f"Enabled ({nod.get('daysInterval')}d)" if nod.get("enabled") else "Disabled"
    out["WS_VM"] = on_off((ss.get("virtualMachineImages") or {}).get("enabled"))
    out["WS_CMK"] = str(len(((ss.get("aws") or {}).get("snapshotReencryptionSettings") or {}).get("sharedCustomerManagedKeysArnPatterns") or []))
    out["WS_TVOL"] = on_off(((ss.get("aws") or {}).get("workloadScanningUsingTemporaryVolumesSettings") or {}).get("enabled"))
    out["WS_LSAIL"] = on_off(((ss.get("aws") or {}).get("lightsailScanningSettings") or {}).get("enabled"))
    out["WS_LAMB"] = "Enabled" if (((ss.get("aws") or {}).get("lambdaSettings") or {}).get("scannedVersionCount") or 0) > 0 else "Disabled"
    out["WS_TAGS"] = f"{len(srt.get('tags') or [])} tags" if srt.get("tags") else "Disabled"
    out["WS_EXCL"] = f"{len(sex.get('tags') or [])} tag-based exclusions"
    out["WS_CIGS"] = on_off(ss.get("computeResourceGroupMemberScanSamplingEnabled"))
    out["WS_ADE1"] = on_off(((ss.get("azure") or {}).get("privateEndpointKeyVaults") or {}).get("enabled"))
    out["WS_ADE2"] = on_off(((ss.get("azure") or {}).get("privateEndpointKeyVaultsWithFirewall") or {}).get("enabled"))
    out["WS_NRT"] = on_off(et.get("enabled"))
    out["WS_NRTW"] = on_off(et.get("workloadScanningEnabled"))
    out["WS_AFIM"] = on_off(fim.get("enabled"))

    asm = q1.get("asm") or q1.get("externalExposureScannerSettings") or q5.get("externalExposureScannerSettings") or {}
    scanners = asm.get("scanners") or {}
    adv = asm.get("advancedCapabilities") or {}
    def nested_on(obj):
        return on_off(obj.get("isEnabled")) if isinstance(obj, dict) else "N/A"

    out["ASM_ON"] = on_off(asm.get("isEnabled"))
    out["ASM_MODE"] = "Advanced" if (adv.get("isEnabled") or out.get("ASM_MODE") == "Advanced") else "Basic"
    out["ASM_CUST"] = nested_on(scanners.get("customTargets"))
    out["ASM_RECON"] = nested_on(scanners.get("recon")) if scanners.get("recon") else out.get("ASM_RECON", "Enabled")
    out["ASM_CODE"] = nested_on(scanners.get("code"))
    out["ASM_API"] = nested_on(scanners.get("apiSecurity"))
    out["ASM_RS"] = nested_on(scanners.get("runtimeSensor"))
    out["ASM_SAAS"] = nested_on(scanners.get("saas")) if scanners.get("saas") else out.get("ASM_SAAS", "Enabled")

    out["ASM_MISC"] = nested_on(asm.get("misconfigurationScanning"))
    out["ASM_CRED"] = nested_on(asm.get("defaultCredentialsScanning"))
    out["ASM_HPT"] = nested_on(asm.get("highProfileThreatScanning"))
    out["ASM_DAST"] = nested_on(asm.get("dastScanning"))
    out["ASM_VEXP"] = nested_on(asm.get("exploitabilityValidationScanning"))
    out["ASM_EAR"] = nested_on(asm.get("earlyAccessRules"))
    out["ASM_VULN"] = nested_on(asm.get("vulnerabilityScanning"))
    out["ASM_DATA"] = nested_on(asm.get("dataScanning"))
    out["ASM_SEC"] = nested_on(asm.get("secretScanning"))
    # Application Endpoint Exposure Level: live from endpointExposureLevelSettings.policyType
    # (PERMISSIVE / MODERATE / STRICT / CUSTOM). Falls back to "Moderate" if unavailable.
    _eel = (q1.get("endpointExposureLevelSettings") or {}).get("policyType")
    out["ASM_EXPL"] = _eel.title() if isinstance(_eel, str) and _eel else "Moderate"

    out["VS_LVULN"] = on_off(vas.get("latestKernelVersionVulnerabilitiesDetectionEnabled") if vas.get("latestKernelVersionVulnerabilitiesDetectionEnabled") is not None else vas.get("osPackageManagedCodeLibrariesVulnerabilitiesDetectionEnabled"))
    out["VS_OSPKG"] = on_off(vas.get("osPackageManagedCodeLibrariesVulnerabilitiesDetectionEnabled"))
    out["VS_WINB"] = on_off(vas.get("windowsManagedVulnerabilitiesDetectionEnabled"))
    out["VS_GOSTD"] = on_off(vas.get("goStandardLibraryVulnerabilitiesEnabled"))
    out["VS_EXCL"] = on_off(vas.get("legacyCodeLibraryExclusionPathsEnabled"))
    out["VS_RHOS"] = on_off(vas.get("ignoreRedHatOpenshiftContainerLibraryVulnerabilities"))
    out["VS_PIP"] = on_off(vas.get("pipInstalledPythonLibrariesVulnerabilitiesEnabled"))
    out["VS_NPM"] = on_off(vas.get("npmInstalledJavascriptLibrariesVulnerabilitiesEnabled"))

    cl2 = vas.get("codeLibraries") or {}
    out["VS_MANIF"] = ", ".join(cl2.get("manifestFilesLifecycleStages") or []) or "None"
    out["VS_LOCK"] = ", ".join(cl2.get("lockFilesLifecycleStages") or []) or "None"
    out["VS_ARTIF"] = ", ".join(cl2.get("artifactsLifecycleStages") or []) or "None"
    out["VS_MAVEN"] = ", ".join(cl2.get("mavenScopes") or []) or "None"
    out["VS_JSDEP"] = ", ".join(cl2.get("npmScopes") or []) or "None"
    out["VS_GRADL"] = ", ".join(cl2.get("gradleScopes") or []) or "None"

    eol = vas.get("endOfLifeTechnologies") or {}
    out["VS_EOL"] = f"Enabled ({eol.get('upcomingDetectionDays')}d)" if eol.get("upcomingDetectionEnabled") else "Disabled"

    dss_b = dss.get("bucketConfig") or {}
    if dss.get("enabled") is not None:
        out["DSS_ON"] = on_off(dss.get("enabled"))
    if dss_b:
        if dss_b.get("enabled") and dss_b.get("privateBucketsEnabled"):
            out["DSS_BUCK"] = "Enabled (Public & Private)"
        elif dss_b.get("enabled"):
            out["DSS_BUCK"] = "Enabled (Public Only)"
        else:
            out["DSS_BUCK"] = "Disabled"
    out["DSS_VDRV"] = on_off((dss.get("virtualDriveConfig") or {}).get("enabled"))
    out["DSS_PAAS"] = on_off((dss.get("cloudDbConfig") or {}).get("enabled"))
    dw_sb = (dss.get("snowflakeConfigV2") or {}).get("schemaScanEnabled")
    dw_db = (dss.get("databricksConfigV2") or {}).get("schemaScanEnabled")
    out["DSS_DW"] = "Enabled" if (dw_sb or dw_db) else "Disabled"
    out["DSS_BQ"] = on_off((dss.get("bigQueryConfig") or {}).get("enabled"))
    out["DSS_DDB"] = on_off((dss.get("dynamoDbConfig") or {}).get("enabled"))
    out["DSS_SNOW"] = on_off((dss.get("snowflakeConfigV2") or {}).get("schemaScanEnabled"))
    out["DSS_IAAS"] = on_off((dss.get("diskDbConfig") or {}).get("enabled"))
    out["DSS_VMD"] = on_off((dss.get("diskFileConfig") or {}).get("enabled"))
    out["DSS_SLS"] = on_off((dss.get("serverlessConfig") or {}).get("enabled"))
    out["DSS_AIV"] = on_off((dss.get("vertexAiConfig") or {}).get("enabled"))
    out["DSS_AIAO"] = on_off((dss.get("openAiConfig") or {}).get("azureEnabled"))
    out["DSS_AIOA"] = on_off((dss.get("openAiConfig") or {}).get("enabled"))
    out["DSS_SHAD"] = on_off((dss.get("shadowDataConfig") or {}).get("enabled"))

    dss_az = (dss.get("azureStorageAccountConfig") or {})
    out["DSS_AZ1"] = on_off((dss_az.get("privateEndpointGeneralConfig") or {}).get("enabled"))
    out["DSS_AZ2"] = on_off((dss_az.get("privateEndpointWithFirewallConfig") or {}).get("enabled"))
    dss_cdb = (dss.get("azureCosmosDbConfig") or {})
    out["DSS_CDBAZ1"] = on_off((dss_cdb.get("privateEndpointGeneralConfig") or {}).get("enabled"))
    out["DSS_CDBAZ2"] = on_off((dss_cdb.get("privateEndpointWithFirewallConfig") or {}).get("enabled"))

    out["F_TR"] = f"{(q3.get('trOn') or {}).get('totalCount', 0)} on / {(q3.get('trOff') or {}).get('totalCount', 0)} off"
    out["F_DR"] = str((q3.get("drTotal") or {}).get("totalCount", 0))
    out["F_WF"] = f"{(q3.get('wfOn') or {}).get('totalCount', 0)} on / {(q3.get('wfOff') or {}).get('totalCount', 0)} off"
    out["F_AR"] = f"{(q3.get('arOn') or {}).get('totalCount', 0)} on / {(q3.get('arOff') or {}).get('totalCount', 0)} off"

    out["AI_AGENTS_COUNT"] = str((q_ai.get("aiAgents") or q_ai.get("ai_agents") or q1.get("aiAgents") or q1.get("ai_agents") or {}).get("totalCount", 0))
    out["AI_MODELS_COUNT"] = str((q_ai.get("aiModels") or q_ai.get("ai_models") or q1.get("aiModels") or q1.get("ai_models") or {}).get("totalCount", 0))
    out["AI_SERVICES_COUNT"] = str((q_ai.get("aiServices") or q_ai.get("ai_services") or q1.get("aiServices") or q1.get("ai_services") or {}).get("totalCount", 0))
    out["AI_MCP_SERVERS_COUNT"] = str((q_ai.get("aiMcpServers") or q_ai.get("mcpServers") or q_ai.get("ai_mcp") or q1.get("aiMcpServers") or q1.get("ai_mcp") or {}).get("totalCount", 0))
    out["AI_PIPELINES_COUNT"] = str((q_ai.get("aiPipelines") or q_ai.get("ai_pipelines") or q1.get("aiPipelines") or q1.get("ai_pipelines") or {}).get("totalCount", 0))
    out["AI_GUARDRAILS_COUNT"] = str((q_ai.get("aiGuardrails") or q_ai.get("ai_guardrails") or q1.get("aiGuardrails") or q1.get("ai_guardrails") or {}).get("totalCount", 0))
    out["AI_DATASETS_COUNT"] = str((q_ai.get("aiDatasets") or q_ai.get("ai_datasets") or q1.get("aiDatasets") or q1.get("ai_datasets") or {}).get("totalCount", 0))
    out["AI_TECHNOLOGIES_COUNT"] = str((q_ai.get("aiTechnologies") or q_ai.get("ai_tech") or q1.get("aiTechnologies") or q1.get("ai_tech") or {}).get("totalCount", 0))
    out["AI_CA_COUNT"] = str((q_ai.get("aiCodingAgents") or q_ai.get("codingAgents") or q_ai.get("ai_ca") or q1.get("aiCodingAgents") or q1.get("ai_ca") or {}).get("totalCount", 0))
    out["AI_CODE_REPOS_COUNT"] = str((q_ai.get("aiCodeRepos") or q_ai.get("codeRepoWithAi") or q_ai.get("ai_repos") or q1.get("aiCodeRepos") or q1.get("ai_repos") or {}).get("totalCount", 0))
    out["AI_WORKLOADS_COUNT"] = str((q_ai.get("aiWorkloads") or q_ai.get("aiWorkloadsTotal") or q_ai.get("ai_workloads") or q1.get("aiWorkloads") or q1.get("ai_workloads") or {}).get("totalCount", 0))

    ca_nodes = (q3.get("cloudAccounts") or q1.get("cloudAccounts") or {}).get("nodes", [])
    if ca_nodes:
        ca_counts = collections.Counter(n.get("cloudProvider") for n in ca_nodes)
        out["C_AWS"] = str(ca_counts.get("AWS", 0))
        out["C_AZ"] = str(ca_counts.get("Azure", 0))
        out["C_GCP"] = str(ca_counts.get("GCP", 0))
        major = {"AWS", "Azure", "GCP"}
        oth_counts = sum(v for k, v in ca_counts.items() if k not in major)
        out["C_OTH"] = str(oth_counts)
        top_oth_names = [k for k, v in ca_counts.items() if k not in major and k]
        out["C_OTH_NAMES"] = ", ".join(top_oth_names[:6])

    # --- Connectors & Deployments & Outposts & Sensors ---
    con_data = q3.get("connectors") or q1.get("connectors") or {}
    con_nodes = con_data.get("nodes", [])
    if con_data.get("totalCount") is not None:
        out["CON_TOT"] = str(con_data.get("totalCount", len(con_nodes)))
    if con_nodes:
        con_statuses = collections.Counter(n.get("status") for n in con_nodes)
        out["CON_EN"] = str(con_statuses.get("CONNECTED", 0))
        out["CON_DIS"] = str(con_statuses.get("DISABLED", 0))
        out["CON_BRO"] = str(con_statuses.get("ERROR", 0))
        k8s_types = {"Amazon Elastic Kubernetes Service (EKS)", "Azure Kubernetes Service (AKS)", "Google Kubernetes Engine (GKE)", "Self-managed Kubernetes", "Kubernetes"}
        vcs_types = {"GitHub", "Azure DevOps", "GitLab", "Bitbucket Cloud"}
        reg_types = {"Amazon Elastic Container Registry (ECR)", "Azure Container Registry (ACR)", "Google Artifact Registry (GAR)", "Google Container Register (GCR)", "GitHub Container Registry (GHCR)", "Container Registry", "Docker Hub Container Registry"}
        
        k8s_cnt = sum(1 for n in con_nodes if ((n.get("type") or {}).get("name") in k8s_types))
        vcs_cnt = sum(1 for n in con_nodes if ((n.get("type") or {}).get("name") in vcs_types))
        reg_cnt = sum(1 for n in con_nodes if ((n.get("type") or {}).get("name") in reg_types))
        out["CON_K8S"] = str(k8s_cnt)
        out["CON_VCS"] = str(vcs_cnt)
        out["CON_R"] = str(reg_cnt)

        # Connectors With / Without Cloud Events
        ce_keys = ["auditLogMonitorEnabled", "kubernetesAuditLogsMonitorEnabled", "dnsLogMonitorEnabled", "networkLogMonitorEnabled", "securityLakeMonitorEnabled", "cloudEventsEnabled", "cloudTrailEnabled", "activityLogsEnabled"]
        with_ce = sum(1 for n in con_nodes if any((n.get("extraConfig") or {}).get(k) is True for k in ce_keys))
        out["CON_WE"] = str(with_ce)
        out["CON_NE"] = str(max(0, len(con_nodes) - with_ce))

    # Deployments breakdown (Broker, Admission Controllers)
    dep_data = q3.get("deployments") or {}
    dep_nodes = dep_data.get("nodes", [])
    if dep_nodes:
        dep_types = collections.Counter(n.get("type") for n in dep_nodes)
        if dep_types.get("BROKER"):
            out["CON_BRO"] = str(dep_types["BROKER"])
        if dep_types.get("ADMISSION_CONTROLLER"):
            out["CON_ADM"] = str(dep_types["ADMISSION_CONTROLLER"])

    # Outposts & Sensors
    outpost_data = q3.get("outposts") or {}
    if outpost_data.get("totalCount") is not None:
        out["OUT_DEP"] = str(outpost_data.get("totalCount", 0))
    sensor_data = q3.get("sensors") or {}
    if sensor_data.get("totalCount") is not None:
        out["L_SE"] = str(sensor_data.get("totalCount", 0))

    # Billable Workload Trend (License metrics: prioritize most recent finalized static data point)
    bwt = q3.get("billableWorkloadTrendV2") or {}
    if bwt:
        dps = bwt.get("dataPoints") or []
        # Filter for latest finalized data point (skip in-progress 0 counts from current uncompleted day)
        valid_dps = [dp for dp in dps if ((dp.get("computeWorkloadCount") or 0) > 0 or (dp.get("serverlessCount") or 0) > 0 or (dp.get("serverlessContainerCount") or 0) > 0 or (dp.get("sensorWorkloadCount") or 0) > 0)]
        last_dp = valid_dps[-1] if valid_dps else (dps[-1] if dps else {})
        
        # Static snapshot from latest finalized dataPoint (fallback to averages only if dataPoints is empty)
        sl_ct = last_dp.get("serverlessContainerCount") if last_dp.get("serverlessContainerCount") is not None else bwt.get("averageServerlessContainerCount")
        sl_fn = last_dp.get("serverlessCount") if last_dp.get("serverlessCount") is not None else bwt.get("averageServerlessCount")
        wos = last_dp.get("wizOsWorkloadCount") if last_dp.get("wizOsWorkloadCount") is not None else bwt.get("wizOsWorkloadCount")
        
        if sl_ct is not None:
            out["SERVERLESS_CT_COUNT"] = fmt_r(sl_ct)
        if sl_fn is not None:
            out["SERVERLESS_FN_COUNT"] = str(sl_fn)
        if wos is not None:
            out["CON_WOS"] = str(wos)
            out["WIZOS_WORKLOAD_COUNT"] = str(wos)
        # Total compute workloads -- denominator for WizOS adoption % (slide 4 Cloud Advanced).
        cw_total = last_dp.get("computeWorkloadCount") if last_dp.get("computeWorkloadCount") is not None else bwt.get("averageComputeWorkloadCount")
        if cw_total is not None:
            out["COMPUTE_WL_TOTAL"] = str(int(cw_total))
        if (bwt.get("greenAgentWorkloadDetails") or {}).get("runCount") is not None:
            out["GREEN_AGENT_RUNS"] = str(bwt["greenAgentWorkloadDetails"]["runCount"])
        
        sensor_cnt = last_dp.get("sensorWorkloadCount") if last_dp.get("sensorWorkloadCount") is not None else bwt.get("averageSensorWorkloadCount")
        if sensor_cnt is not None and not out.get("L_SE"):
            out["L_SE"] = str(sensor_cnt)

    # Fallbacks for serverless
    sf_cnt = (q3.get("serverless") or q1.get("serverless") or {}).get("totalCount")
    if sf_cnt is not None and not out.get("SERVERLESS_FN_COUNT"):
        out["SERVERLESS_FN_COUNT"] = str(sf_cnt)

    cli_cnt = (q3.get("cliScans") or q1.get("cliScans") or {}).get("totalCount")
    if cli_cnt is not None:
        out["CLI"] = fmt_r(cli_cnt)

    k8s_data = q3.get("k8sClusters") or q1.get("k8sClusters") or {}
    k8s_nodes = k8s_data.get("nodes", [])
    k8s_tot_q = (q3.get("totalClusters") or q1.get("totalClusters") or {}).get("totalCount")
    k8s_tot = k8s_tot_q if k8s_tot_q is not None else (k8s_data.get("totalCount") if k8s_data.get("totalCount") is not None else len(k8s_nodes))
    if k8s_tot:
        out["K8S"] = str(k8s_tot)
        out["K8C_TOT"] = str(k8s_tot)
        
        # Canonical deploymentCoverage_* properties (falling back to node inspections)
        kc_wc_val = (q3.get("kc_wc") or q1.get("kc_wc") or {}).get("totalCount")
        kc_ac_val = (q3.get("kc_ac") or q1.get("kc_ac") or {}).get("totalCount")
        kc_se_val = (q3.get("kc_se") or q1.get("kc_se") or {}).get("totalCount")
        kc_cli_val = (q3.get("kc_cli") or q1.get("kc_cli") or {}).get("totalCount")

        kg_nc_val = (q3.get("kg_nc") or q1.get("kg_nc") or {}).get("totalCount")
        kg_na_val = (q3.get("kg_na") or q1.get("kg_na") or {}).get("totalCount")
        kg_ns_val = (q3.get("kg_ns") or q1.get("kg_ns") or {}).get("totalCount")

        out["KC_WC"] = str(kc_wc_val if kc_wc_val is not None else sum(1 for c in k8s_nodes if c.get("connectors") and any(con.get("enabled") for con in c.get("connectors", []))))
        out["KC_AC"] = str(kc_ac_val if kc_ac_val is not None else sum(1 for c in k8s_nodes if c.get("admissionController")))
        out["KC_SE"] = str(kc_se_val if kc_se_val is not None else sum(1 for c in k8s_nodes if c.get("kubernetesAuditLogCollector")))
        out["KC_CLI"] = str(kc_cli_val if kc_cli_val is not None else sum(1 for c in k8s_nodes if c.get("sensorGroup")))

        out["KG_NC"] = str(kg_nc_val if kg_nc_val is not None else max(0, k8s_tot - int(out["KC_WC"])))
        out["KG_NA"] = str(kg_na_val if kg_na_val is not None else max(0, k8s_tot - int(out["KC_SE"])))
        out["KG_NS"] = str(kg_ns_val if kg_ns_val is not None else max(0, k8s_tot - int(out["KC_CLI"])))
    if k8s_nodes:
        kind_map = {"EKS": "EKS", "AKS": "AKS", "GKE": "GKE", "SELF_HOSTED": "Self-hosted", "ACK": "ACK", "OPEN_SHIFT": "OpenShift"}
        k_counts = collections.Counter(kind_map.get(n.get("kind"), n.get("kind") or "Other") for n in k8s_nodes)
        top_k = k_counts.most_common()
        for i in range(5):
            if i < len(top_k):
                out[f"K8S_{i+1}"] = top_k[i][0]
                out[f"K8C_{i+1}"] = str(top_k[i][1])
            else:
                out[f"K8S_{i+1}"] = ""
                out[f"K8C_{i+1}"] = ""
        oth_k = sum(c[1] for c in top_k[5:])
        out["K8C_OTH"] = str(oth_k)

    r_nodes = (q1.get("registries") or q3.get("registries") or {}).get("nodes", [])
    r_tot_val = (q1.get("registries") or q3.get("registries") or {}).get("totalCount") or len(r_nodes)
    if r_tot_val:
        out["R_TOT"] = str(r_tot_val)

    # Cloud Events breakdown (CLOUD_EVENTS_1..13 and CE_1..13)
    origin_display = {
        "WIZ_WORKLOAD_SSH_LOGS": "Workload SSH Logs",
        "WIZ_SENSOR_RUNTIME_EVENTS": "Wiz Sensor Runtime",
        "AWS_CLOUDTRAIL": "AWS CloudTrail",
        "WIZ_WORKLOAD_VIRTUAL_APPLIANCE_LOGS": "Virtual Appliance Logs",
        "GCP_GKE_AUDIT_LOGS": "GCP GKE Audit Logs",
        "WIZ_AUDIT_LOGS": "Wiz Audit Logs",
        "WORKLOAD_LOGS": "Workload Logs",
        "WIZ_WORKLOAD_HTTP_LOGS": "Workload HTTP Logs",
        "AWS_S3_DATA_EVENTS": "AWS S3 Data Events",
        "GCP_AUDIT_LOGS": "GCP Audit Logs",
        "GCP_VPC_FLOW_LOGS": "GCP VPC Flow Logs",
        "WIZ_SENSOR": "Wiz Sensor Detection",
        "WIZ_SENSOR_TLS_ACTIVITY": "Wiz Sensor TLS Activity",
        "AWS_VPC_FLOW_LOGS": "AWS VPC Flow Logs",
        "GCP_CLOUD_DNS_LOGS": "GCP Cloud DNS Logs",
        "WIZ_ADMISSION_CONTROLLER": "Wiz Admission Controller",
        "WIZ_WORKLOAD_DATABASE_LOGS": "Workload DB Logs",
        "WIZ_KUBERNETES_AUDIT_LOGS_COLLECTOR": "Wiz K8s Audit Collector",
        "AZURE_ACTIVE_DIRECTORY": "Azure AD / Entra ID",
        "AZURE_STORAGE_ACCOUNT": "Azure Storage Logs",
        "AZURE_ACTIVITY_LOGS": "Azure Activity Logs",
        "GOOGLE_WORKSPACE_AUDIT_LOGS": "Google Workspace",
        "GCP_STORAGE_DATA_ACCESS_LOGS": "GCP Storage Access",
        "OKTA_SYSTEM_LOGS": "Okta Logs",
        "GITHUB_AUDIT_LOGS": "GitHub Audit Logs",
        "OCI_AUDIT_LOGS": "OCI Audit Logs",
        "AZURE_DEFENDER_FOR_CLOUD": "Azure Defender",
        "AWS_GUARD_DUTY": "AWS GuardDuty",
        "GCP_SECURITY_COMMAND_CENTER": "GCP SCC",
        "AWS_EKS_AUDIT_LOGS": "AWS EKS Audit Logs",
        "AZURE_AKS_AUDIT_LOGS": "Azure AKS Audit Logs",
        "AZURE_KEY_VAULT": "Azure Key Vault",
    }
    
    ce_nodes = (q3.get("cloudEvents") or {}).get("nodes", [])
    ce_list = []
    for n in ce_nodes:
        vals = n.get("values") or []
        orig = vals[0] if vals else ""
        cnt = n.get("countV2") or 0
        if orig and cnt > 0:
            ce_list.append((orig, cnt))
    
    # Fallback to cloudEventRules if cloudEvents not present
    if not ce_list:
        ce_rules = (q3.get("cloudEventRules") or {}).get("nodes", [])
        ce_counts = collections.defaultdict(int)
        for r in ce_rules:
            cnt = r.get("matchedEventCount") or 0
            for orig in (r.get("origins") or ["Other"]):
                ce_counts[orig] += cnt
        ce_list = list(ce_counts.items())

    ce_list.sort(key=lambda x: x[1], reverse=True)

    for i in range(13):
        slot = i + 1
        if i < len(ce_list):
            orig, cnt = ce_list[i]
            disp = origin_display.get(orig, orig.replace("_", " ").title())
            out[f"CLOUD_EVENTS_{slot}"] = disp
            out[f"CE_{slot}"] = fmt_big(cnt) if cnt else ""
        else:
            out[f"CLOUD_EVENTS_{slot}"] = ""
            out[f"CE_{slot}"] = ""

    fw_en = (q5.get("customFrameworksEnabled") or q3.get("customFrameworksEnabled") or q1.get("customFrameworksEnabled") or {}).get("totalCount")
    fw_all = (q5.get("customFrameworksAll") or q3.get("customFrameworksAll") or q1.get("customFrameworksAll") or {}).get("totalCount")
    if fw_en is not None:
        out["F_FW"] = str(fw_en)
    elif fw_all is not None:
        out["F_FW"] = str(fw_all)

    ai_settings = q5.get("aiSettings") or q3.get("aiSettings") or q1.get("aiSettings") or {}
    red_agent_on = (ai_settings.get("redAgent") or {}).get("isEnabled")
    out["F_RA"] = "Yes" if red_agent_on is True else "No" if red_agent_on is False else "N/A"
    ai_agent_nodes = (q5.get("aiAgentsList") or q3.get("aiAgentsList") or q1.get("aiAgentsList") or q5.get("aiAgents") or q3.get("aiAgents") or q1.get("aiAgents") or {}).get("nodes", [])
    def agent_on(name):
        if not ai_agent_nodes:
            return "N/A"
        a = next((x for x in ai_agent_nodes if x and x.get("name") == name), None)
        if not a:
            return "N/A"
        return "Yes" if a.get("enabled") else "No"
    out["F_BA"] = agent_on("Blue Agent")
    out["F_GA"] = agent_on("Green Agent")

    be_audit = q5.get("browserExtensionAudit") or q3.get("browserExtensionAudit") or q1.get("browserExtensionAudit")
    if be_audit is not None and isinstance(be_audit, dict) and "nodes" in be_audit:
        be_nodes = be_audit.get("nodes") or []
        be_chrome = next((n for n in be_nodes if n.get("clientType") == "WIZ_CHROME_EXTEND"), None)
        if be_chrome:
            be_users = (be_chrome.get("analytics") or {}).get("performerCount", 0)
            out["F_BE"] = str(be_users)
        else:
            out["F_BE"] = "0"
    else:
        out["F_BE"] = "No Permission"

    mcp_audit = q5.get("mcpAudit") or q3.get("mcpAudit") or q1.get("mcpAudit")
    if mcp_audit is not None and isinstance(mcp_audit, dict) and "totalCount" in mcp_audit:
        mcp_users = mcp_audit.get("totalCount")
        out["F_WMCP"] = str(mcp_users if mcp_users is not None else 0)
    else:
        out["F_WMCP"] = "No Permission"

    def fmt_date_str(dt_str):
        if not dt_str:
            return ""
        try:
            parts = dt_str.split("T")[0].split("-")
            if len(parts) == 3:
                return f"{parts[1]}-{parts[2]}-{parts[0]}"
        except Exception:
            pass
        return dt_str

    int_dep = (q5.get("integrationDeployments") or q3.get("integrationDeployments") or q1.get("integrationDeployments") or {}).get("nodes", [])
    if not int_dep:
        dep_nodes = (q5.get("deployments") or q3.get("deployments") or q1.get("deployments") or {}).get("nodes", [])
        int_dep = [n for n in dep_nodes if n.get("type") == "INTEGRATION"]

    sorted_ints = sorted(int_dep, key=lambda x: x.get("lastSeenAt") or (x.get("object") or {}).get("lastActivityAt") or "", reverse=True)
    for i in range(10):
        idx = i + 1
        if i < len(sorted_ints):
            n = sorted_ints[i]
            out[f"IA_{idx}"] = n.get("name", "")
            ls = n.get("lastSeenAt") or (n.get("object") or {}).get("lastActivityAt")
            out[f"IR_{idx}"] = fmt_date_str(ls)
        else:
            out[f"IA_{idx}"] = ""
            out[f"IR_{idx}"] = ""

    out["F_IR"] = str((q3.get("irTotal") or {}).get("totalCount", 0))
    out["F_PP"] = str((q3.get("ppUser") or {}).get("totalCount", 0))
    out["F_MM"] = str((q3.get("mmUser") or {}).get("totalCount", 0))

    # --- Tenant License & Contract Information ---
    t_info = (q3.get("viewerV2") or q1.get("viewerV2") or q5.get("viewerV2") or {}).get("tenant") or {}
    t_created = t_info.get("createdAt")
    if t_created:
        try:
            c_dt = datetime.strptime(t_created[:10], "%Y-%m-%d")
            now_dt = datetime.now()
            out["CUS_NOD"] = str(max(0, (now_dt - c_dt).days))
        except Exception:
            pass

    p_lic = t_info.get("primaryLicense") or {}
    t_end = p_lic.get("endAt")
    if not t_end:
        for lic in (t_info.get("licenses") or []):
            if lic.get("status") == "ACTIVE" and lic.get("endAt"):
                t_end = lic.get("endAt")
                break
    if t_end:
        try:
            e_dt = datetime.strptime(t_end[:10], "%Y-%m-%d")
            now_dt = datetime.now()
            out["D_U_R"] = str(max(0, (e_dt - now_dt).days))
            out["RENEWAL_DATE"] = t_end[:10]
            parts = t_end[:10].split("-")
            if len(parts) == 3:
                out["CONTRACT_END_FMT"] = f"{parts[1]}/{parts[2]}/{parts[0]}"
        except Exception:
            pass

    # --- System Health Issues ---
    shi_op_c = (q5.get("shi_open_crit") or q1.get("shi_open_crit") or {}).get("totalCount")
    shi_op_h = (q5.get("shi_open_high") or q1.get("shi_open_high") or {}).get("totalCount")
    shi_re_c = (q5.get("shi_res_crit") or q1.get("shi_res_crit") or {}).get("totalCount")
    shi_re_h = (q5.get("shi_res_high") or q1.get("shi_res_high") or {}).get("totalCount")
    
    out["SHI_C"] = str(shi_op_c if shi_op_c is not None else 0)
    out["SHI_H"] = str(shi_op_h if shi_op_h is not None else 0)
    out["SHI_R_C"] = str(shi_re_c if shi_re_c is not None else 0)
    out["SHI_R_H"] = str(shi_re_h if shi_re_h is not None else 0)

    # Granular SHI by Resource Bucket
    shi_op = (q5.get("shi_op") or q_shi.get("shi_op") or {}).get("totalCount")
    shi_cc = (q5.get("shi_cc") or q_shi.get("shi_cc") or {}).get("totalCount")
    shi_int = (q5.get("shi_int") or q_shi.get("shi_int") or {}).get("totalCount")
    shi_reg = (q5.get("shi_reg") or q_shi.get("shi_reg") or {}).get("totalCount")
    shi_k8s = (q5.get("shi_k8s") or q_shi.get("shi_k8s") or {}).get("totalCount")
    shi_vcs = (q5.get("shi_vcs") or q_shi.get("shi_vcs") or {}).get("totalCount")
    shi_brk = (q5.get("shi_brk") or q_shi.get("shi_brk") or {}).get("totalCount")

    out["SHI_O"] = fmt_r(shi_op if shi_op is not None else 0)
    out["SHI_CC"] = fmt_r(shi_cc if shi_cc is not None else 0)
    out["SHI_I"] = fmt_r(shi_int if shi_int is not None else 0)
    out["SHI_RC"] = fmt_r(shi_reg if shi_reg is not None else 0)
    out["SHI_KC"] = fmt_r(shi_k8s if shi_k8s is not None else 0)
    out["SHI_VCS"] = fmt_r(shi_vcs if shi_vcs is not None else 0)
    out["SHI_B"] = fmt_r(shi_brk if shi_brk is not None else 0)

    # --- Licenses (Defend & Code) ---
    all_lics = t_info.get("licenses") or []
    has_code_lic = any(l.get("sku") == "CODE" and l.get("status") == "ACTIVE" for l in all_lics)
    has_defend_lic = any(l.get("sku") in ("DEFEND", "DEFEND_INGESTION", "RUNTIME_SENSOR") and l.get("status") == "ACTIVE" for l in all_lics)
    
    out["L_CO"] = out.get("CL_CODE") if out.get("CL_CODE") and out["CL_CODE"] != "0" else ("Active" if has_code_lic else "0")
    out["L_DE"] = "Active" if has_defend_lic else (out.get("L_SE") if out.get("L_SE") and out["L_SE"] != "0" else "0")

    # --- Granular Data Scans ---
    ds_b_cnt = (q5.get("ds_bucket") or q1.get("ds_bucket") or {}).get("totalCount")
    ds_db_cnt = (q5.get("ds_db") or q1.get("ds_db") or {}).get("totalCount")
    ds_dw_cnt = (q5.get("ds_dw") or q1.get("ds_dw") or {}).get("totalCount")
    ds_vd_cnt = (q5.get("ds_vdrv") or q1.get("ds_vdrv") or {}).get("totalCount")
    ds_ai_cnt = (q5.get("ds_ai") or q1.get("ds_ai") or {}).get("totalCount")
    ds_fss_cnt = (q5.get("ds_fss") or q1.get("ds_fss") or {}).get("totalCount")

    out["DS_B"] = fmt_r(ds_b_cnt if ds_b_cnt is not None else 0)
    out["DS_PD"] = fmt_r(ds_db_cnt if ds_db_cnt is not None else 0)
    out["DS_DW"] = fmt_r(ds_dw_cnt if ds_dw_cnt is not None else 0)
    out["DS_VD"] = fmt_r(ds_vd_cnt if ds_vd_cnt is not None else 0)
    out["DS_AI"] = fmt_r(ds_ai_cnt if ds_ai_cnt is not None else 0)
    out["DS_FSS"] = fmt_r(ds_fss_cnt if ds_fss_cnt is not None else 0)

    # --- Non-OS Disk Scans ---
    non_t_raw = (q5.get("non_os_total") or q1.get("non_os_total") or {}).get("totalCount")
    non_succ = (q5.get("non_os_success") or q1.get("non_os_success") or {}).get("totalCount")
    non_fail = (q5.get("non_os_failed") or q1.get("non_os_failed") or {}).get("totalCount")
    non_skip = (q5.get("non_os_skipped") or q1.get("non_os_skipped") or {}).get("totalCount")

    non_calc_t = (non_succ or 0) + (non_fail or 0) + (non_skip or 0)
    non_t = non_calc_t if non_calc_t > (non_t_raw or 0) else (non_t_raw or 0)

    out["NON_T"] = fmt_r(non_t)
    out["NON_S"] = fmt_r(non_skip or 0)  # User directive: *_S represents Skipped
    out["NON_SK"] = fmt_r(non_skip or 0)
    out["NON_F"] = fmt_r(non_fail or 0)
    out["NON_SUCC"] = fmt_r(non_succ or 0)
    if non_t > 0:
        non_cov = non_succ if non_succ is not None else max(0, non_t - (non_fail or 0) - (non_skip or 0))
        out["NON_C"] = f"{int(math.floor(non_cov / non_t * 100))}%"
        out["NON_P"] = out["NON_C"]
    else:
        out["NON_C"] = "N/A"
        out["NON_P"] = "N/A"

    # --- Registry Container Image Scans ---
    rci_t_raw = (q5.get("rci_total") or q1.get("rci_total") or {}).get("totalCount")
    rci_succ = (q5.get("rci_success") or q1.get("rci_success") or {}).get("totalCount")
    rci_fail = (q5.get("rci_failed") or q1.get("rci_failed") or {}).get("totalCount")
    rci_skip = (q5.get("rci_skipped") or q1.get("rci_skipped") or {}).get("totalCount")

    rci_calc_t = (rci_succ or 0) + (rci_fail or 0) + (rci_skip or 0)
    rci_t = rci_calc_t if rci_calc_t > (rci_t_raw or 0) else (rci_t_raw or 0)

    out["RCI_T"] = fmt_r(rci_t)
    out["RCI_S"] = fmt_r(rci_skip or 0)  # User directive: *_S represents Skipped
    out["RCI_SK"] = fmt_r(rci_skip or 0)
    out["RCI_F"] = fmt_r(rci_fail or 0)
    out["RCI_SUCC"] = fmt_r(rci_succ or 0)
    if rci_t > 0:
        rci_cov = rci_succ if rci_succ is not None else max(0, rci_t - (rci_fail or 0) - (rci_skip or 0))
        out["RCI_C"] = f"{int(math.floor(rci_cov / rci_t * 100))}%"
        out["RCI_P"] = out["RCI_C"]
    else:
        out["RCI_C"] = "N/A"
        out["RCI_P"] = "N/A"

    # --- VM Image Workload Scans ---
    vmi_t_raw = (q5.get("vmi_total") or q1.get("vmi_total") or {}).get("totalCount")
    vmi_succ = (q5.get("vmi_success") or q1.get("vmi_success") or {}).get("totalCount")
    vmi_fail = (q5.get("vmi_failed") or q1.get("vmi_failed") or {}).get("totalCount")
    vmi_skip = (q5.get("vmi_skipped") or q1.get("vmi_skipped") or {}).get("totalCount")

    vmi_calc_t = (vmi_succ or 0) + (vmi_fail or 0) + (vmi_skip or 0)
    vmi_t = vmi_calc_t if vmi_calc_t > (vmi_t_raw or 0) else (vmi_t_raw or 0)

    out["VMI_T"] = fmt_r(vmi_t)
    out["VMI_S"] = fmt_r(vmi_skip or 0)  # User directive: *_S represents Skipped
    out["VMI_SK"] = fmt_r(vmi_skip or 0)
    out["VMI_F"] = fmt_r(vmi_fail or 0)
    out["VMI_SUCC"] = fmt_r(vmi_succ or 0)
    if vmi_t > 0:
        vmi_cov = vmi_succ if vmi_succ is not None else max(0, vmi_t - (vmi_fail or 0) - (vmi_skip or 0))
        out["VMI_C"] = f"{int(math.floor(vmi_cov / vmi_t * 100))}%"
        out["VMI_P"] = out["VMI_C"]
    else:
        out["VMI_C"] = "N/A"
        out["VMI_P"] = "N/A"

    # --- Data Scans Defaults (so never blank) ---
    if not out.get("DS_T"):
        out["DS_T"] = "0"
        out["DS_F"] = "0"
        out["DS_SK"] = "0"
        out["DS_P"] = "N/A"

    # --- Red Agent Scans Defaults ---
    if not out.get("RA_DAST"):
        out["RA_DAST"] = "0"
    if not out.get("RA_WC"):
        out["RA_WC"] = "0"
    if not out.get("RA_SI"):
        out["RA_SI"] = "0"
    if not out.get("ASM_SV"):
        out["ASM_SV"] = "Disabled"
    if not out.get("RA_TOTS"):
        out["RA_TOTS"] = "0"

    # --- Integrations from integrationsList ---
    raw_ints = (q5.get("integrationsList") or {}).get("nodes", [])
    if raw_ints:
        # Sort by lastActivityAt or lastTestedAt
        sorted_ints = sorted(raw_ints, key=lambda x: x.get("lastActivityAt") or x.get("lastTestedAt") or "", reverse=True)
        for i in range(10):
            idx = i + 1
            if i < len(sorted_ints):
                n = sorted_ints[i]
                out[f"IA_{idx}"] = n.get("name", "")
                ls = n.get("lastActivityAt") or n.get("lastTestedAt")
                out[f"IR_{idx}"] = fmt_date_str(ls)
            else:
                out[f"IA_{idx}"] = ""
                out[f"IR_{idx}"] = ""

    # --- Q2 ---
    out["OC"] = fmt_r((q2.get("ocIssues") or {}).get("totalCount", 0))
    out["OH"] = fmt_r((q2.get("ohIssues") or {}).get("totalCount", 0))
    out["RC"] = fmt_r((q2.get("rcIssues") or {}).get("totalCount", 0))
    out["RH"] = fmt_r((q2.get("rhIssues") or {}).get("totalCount", 0))
    out["RJ"] = fmt_r((q2.get("rjIssues") or {}).get("totalCount", 0))

    # Defend / Sensor license & availability check for Threat metrics (OT, RT, MTTR_O)
    viewer = q3.get("viewerV2") or q1.get("viewerV2") or q2.get("viewerV2") or q5.get("viewerV2") or {}
    licenses = (viewer.get("tenant") or {}).get("licenses", [])
    active_skus = {l.get("sku") for l in licenses if l and l.get("status") == "ACTIVE"}
    defend_skus = {"DEFEND", "WIZ_DEFEND", "RUNTIME_SENSOR", "SENSOR", "ONE", "UNLIMITED_CLOUD_EVENTS_VOLUME"}
    sensor_count = (q3.get("sensors") or q1.get("sensors") or {}).get("totalCount") or 0

    has_defend_or_sensor = bool(active_skus & defend_skus) or sensor_count > 0 or len(active_skus) == 0
    ot_raw = q2.get("otIssues")
    rt_raw = q2.get("rtIssues")

    mttr_s = q2.get("mttr")[0] if isinstance(q2.get("mttr"), list) and len(q2["mttr"]) > 0 else q2.get("mttr") or {}
    mttr_dps = mttr_s.get("dataPoints") or []
    mttr_last = mttr_dps[-1] if len(mttr_dps) > 0 else {}

    if not has_defend_or_sensor or ot_raw is None:
        out["OT"] = "N/A"
        out["RT"] = "N/A"
        out["MTTR_O"] = "N/A"
    else:
        out["OT"] = fmt_r(ot_raw.get("totalCount", 0))
        out["RT"] = fmt_r(rt_raw.get("totalCount", 0)) if rt_raw is not None else "N/A"
        out["MTTR_O"] = sec2days(mttr_s.get("total") if mttr_s.get("total") is not None else mttr_last.get("totalValue"))
    out["MTTR_C"] = sec2days(mttr_last.get("criticalSeverityValue"))
    out["MTTR_H"] = sec2days(mttr_last.get("highSeverityValue"))

    age_s = q2.get("avgAge")[0] if isinstance(q2.get("avgAge"), list) and len(q2["avgAge"]) > 0 else q2.get("avgAge") or {}
    age_dps = age_s.get("dataPoints") or []
    age_last = age_dps[-1] if age_dps else (age_dps[0] if age_dps else {})
    crit_sec = age_last.get("criticalSeverityValue")
    high_sec = age_last.get("highSeverityValue")
    if crit_sec is not None:
        out["AVG_AGEC"] = str(round(float(crit_sec) / 86400.0))
    if high_sec is not None:
        out["AVG_AGEH"] = str(round(float(high_sec) / 86400.0))

    # --- Top Controls by Issue Count (Slide 11: Critical & High) ---
    def extract_top_controls(group_nodes):
        results = []
        for n in group_nodes:
            cnt = (n.get("issues") or {}).get("totalCount", 0)
            issue_nodes = (n.get("issues") or {}).get("nodes") or []
            name = None
            if issue_nodes:
                sr = issue_nodes[0].get("sourceRules") or []
                for r in sr:
                    if r.get("name"):
                        name = r.get("name")
                        break
                    elif (r.get("control") or {}).get("name"):
                        name = r.get("control", {}).get("name")
                        break
            if not name:
                name = n.get("id")
            results.append((name, cnt))
        results.sort(key=lambda x: x[1], reverse=True)
        return results

    crit_ctrl_nodes = ((q3.get("criticalControls") or q2.get("criticalControls") or q1.get("criticalControls") or {}).get("nodes") or [])
    top_crit = extract_top_controls(crit_ctrl_nodes)
    if len(top_crit) == 0:
        for idx in [1, 2, 3]:
            out[f"CI_CONTROL_{idx}"] = "No current open Critical Issues in environment ✅"
            out[f"CI_CBC_{idx}"] = ""
    else:
        for i in range(3):
            idx = i + 1
            if i < len(top_crit):
                out[f"CI_CONTROL_{idx}"] = top_crit[i][0]
                out[f"CI_CBC_{idx}"] = fmt_r(top_crit[i][1])
            else:
                out[f"CI_CONTROL_{idx}"] = ""
                out[f"CI_CBC_{idx}"] = ""

    high_ctrl_nodes = ((q3.get("highControls") or q2.get("highControls") or q1.get("highControls") or {}).get("nodes") or [])
    top_high = extract_top_controls(high_ctrl_nodes)
    for i in range(3):
        idx = i + 1
        if i < len(top_high):
            out[f"HI_CONTROL_{idx}"] = top_high[i][0]
            out[f"HI_CBC_{idx}"] = fmt_r(top_high[i][1])
        else:
            out[f"HI_CONTROL_{idx}"] = ""
            out[f"HI_CBC_{idx}"] = ""

    # --- Q5: Data Scans & Red Agent Analytics ---
    q5_or_q1 = q5 if q5 else q1
    ds_tot = (q5_or_q1.get("ds_total") or {}).get("totalCount")
    ds_fail = (q5_or_q1.get("ds_failed") or {}).get("totalCount")
    ds_skip = (q5_or_q1.get("ds_skipped") or {}).get("totalCount")
    if ds_tot is not None:
        out["DS_T"] = fmt_r(ds_tot)
        out["DS_F"] = fmt_r(ds_fail or 0)
        out["DS_SK"] = fmt_r(ds_skip or 0)
        if ds_tot > 0:
            coverage = max(0, ds_tot - (ds_fail or 0) - (ds_skip or 0))
            out["DS_P"] = f"{int(math.floor(coverage / ds_tot * 100))}%"

    ra_set = q5_or_q1.get("redAgentSettings") or q1.get("redAgentSettings") or {}
    if ra_set:
        dast_mod = (ra_set.get("dastAttackerModule") or {}).get("isEnabled")
        saas_mod = (ra_set.get("saasAttackerModule") or {}).get("isEnabled")
        sec_mod = (ra_set.get("secretImpactModule") or {}).get("isEnabled")
        crawl_mod = (ra_set.get("webCrawlerModule") or {}).get("isEnabled")
        out["ASM_RECON"] = on_off(dast_mod)
        out["ASM_SAAS"] = on_off(saas_mod)
        out["ASM_SV"] = on_off(sec_mod) if on_off(sec_mod) != "Disabled" else "Disabled"
        out["ASM_MODE"] = "Advanced" if (dast_mod or saas_mod or sec_mod or crawl_mod) else "Basic"

    ra_wc = (q5_or_q1.get("webCrawlerApiEndpoints") or {}).get("totalCount")
    ra_dast = (q5_or_q1.get("webDastAttackerFindings") or {}).get("totalCount")
    ra_issues = (q5_or_q1.get("webDastAttackerIssues") or {}).get("totalCount")
    ra_si = (q5_or_q1.get("secretsBlastRadiusFindings") or {}).get("totalCount")
    if ra_wc is not None:
        out["RA_WC"] = str(ra_wc)
    if ra_dast is not None:
        out["RA_DAST"] = str(ra_dast)
    if ra_si is not None:
        out["RA_SI"] = str(ra_si)
    if any(x is not None for x in [ra_wc, ra_dast, ra_issues, ra_si]):
        out["RA_TOTS"] = str((ra_wc or 0) + (ra_dast or 0) + (ra_issues or 0) + (ra_si or 0))

    # --- Q3 ---
    u_tot = (q3.get("uTot") or {}).get("totalCount", 0)
    u_act = (q3.get("uAct") or {}).get("totalCount", 0)
    out["U_TOT"] = str(u_tot)
    out["U_ACT"] = str(u_act)
    out["U_ENG"] = f"{round((u_act / u_tot) * 100)}%" if u_tot > 0 else "0%"

    sso_counts = {}
    for n in ((q3.get("ssoUsers") or {}).get("nodes") or []):
        idp = ((n.get("identityProviderV2") or {}).get("name")) or "Local"
        sso_counts[idp] = sso_counts.get(idp, 0) + 1
    sorted_sso = sorted(sso_counts.items(), key=lambda x: x[1], reverse=True)
    for i in range(3):
        out[f"SSO_{i+1}"] = f"{sorted_sso[i][0]} ({sorted_sso[i][1]})" if i < len(sorted_sso) else ""

    p_tot = q3.get("pTot") or {}
    p_root = q3.get("pRoot") or {}
    out["P_TOT"] = str(p_tot.get("totalCount", 0))
    out["P_HBI"] = str(p_tot.get("HBICount", 0))
    out["P_MBI"] = str(p_tot.get("MBICount", 0))
    out["P_LBI"] = str(p_tot.get("LBICount", 0))
    out["PC_TOT"] = str((p_tot.get("totalCount") or 0) - (p_root.get("totalCount") or 0))

    cc_items = q3.get("champItems") or []
    cc_owners = []
    mod_labels = []
    per_mod = {}
    for it in cc_items:
        owner_name = "Unassigned" if is_uuid((it.get("owner") or {}).get("name")) else (it.get("owner") or {}).get("name") or "Unassigned"
        lbl = mod_lbl.get(it.get("type"), it.get("type"))
        mod_labels.append(lbl)
        if it.get("type") in cc_var:
            per_mod[cc_var[it["type"]]] = owner_name
        if owner_name and owner_name != "Unassigned":
            cc_owners.append(owner_name)

    for i in range(10):
        out[f"CC_{i+1}"] = cc_owners[i] if i < len(cc_owners) else ""
        out[f"CM_{i+1}"] = mod_labels[i] if i < len(mod_labels) else ""
    out["CC_TOT"] = str(len(cc_items))
    for v in cc_var.values():
        out[v] = per_mod.get(v, "Unassigned")

    out["TC_TOT"] = str(len((q3.get("tcs") or {}).get("supportContacts") or []))

    dp = (((q3.get("secScore") or {}).get("nodes") or [{}])[0].get("dataPoints")) or []
    if len(dp) > 0:
        s1s = dp[0].get("value", 0)
        s1e = dp[-1].get("value", 0)
        delta = round((s1e - s1s) * 10.0) / 10.0
        out["SS"] = str(round(s1e * 10.0) / 10.0)
        out["s1s"] = str(round(s1s * 10.0) / 10.0)
        out["s1e"] = str(round(s1e * 10.0) / 10.0)
        out["s1d"] = f"{'+' if delta > 0 else ''}{delta}"
    else:
        out["SS"] = out["s1s"] = out["s1e"] = out["s1d"] = "N/A"

    bench = (q3.get("ssBench") or {}).get("securityScore") or {}
    sp = None
    for k in ["byIndustry", "byWorkloadCount", "byIndustryAndWorkloadCount"]:
        if bench.get(k) and bench[k].get("percentile50") is not None:
            sp = bench[k]["percentile50"]
            break
    out["SP"] = "N/A" if sp is None else str(round(sp * 10.0) / 10.0)
    try:
        gap = round((float(out["SS"]) - float(out["SP"])) * 10.0) / 10.0
        out["SG"] = f"{'+' if gap > 0 else ''}{gap}"
    except Exception:
        out["SG"] = "N/A"
    out["SS_I"] = ((q3.get("viewerV2") or {}).get("tenant") or {}).get("industry") or "Technology"

    bwt = q3.get("billableWorkloadTrendV2") or {}
    if not out.get("SERVERLESS_FN_COUNT") and bwt.get("averageServerlessCount"):
        out["SERVERLESS_FN_COUNT"] = str(bwt.get("averageServerlessCount"))
    if not out.get("WIZOS_WORKLOAD_COUNT"):
        out["WIZOS_WORKLOAD_COUNT"] = str(bwt.get("wizOsWorkloadCount", 0))
    if not out.get("WORKFLOW_RUNS"):
        out["WORKFLOW_RUNS"] = str((bwt.get("workflowWorkloadDetails") or {}).get("runCount", 0))
    if not out.get("GREEN_AGENT_RUNS"):
        out["GREEN_AGENT_RUNS"] = str((bwt.get("greenAgentWorkloadDetails") or {}).get("runCount", 0))

    # --- Q4 ---
    def parse_techs(resp):
        res = {}
        for n in ((resp.get("graphSearch") or {}).get("nodes") or []):
            ents = n.get("entities") or []
            tech = ents[0] if len(ents) > 0 else None
            cnt = n.get("aggregateCount", 0)
            if not tech or cnt <= 0:
                continue
            res[tech.get("name", "Unknown")] = {"count": cnt, "properties": tech.get("properties") or {}}
        return res

    totals = parse_techs(q4a)
    actives = parse_techs(q4b)
    if len(totals) == 0 and len(q4c_blocks) > 0:
        syn = {}
        for block in q4c_blocks:
            for node in ((block.get("graphSearch") or {}).get("nodes") or []):
                ents = node.get("entities") or []
                if len(ents) < 2:
                    continue
                te = ents[0]
                if te.get("type") != "TECHNOLOGY":
                    continue
                tn = te.get("name", "Unknown")
                if tn not in syn:
                    syn[tn] = {"count": 0, "properties": te.get("properties") or {}}
                syn[tn]["count"] += 1
        totals.update(syn)

    tech_dates = {}
    cutoff90d = datetime.fromtimestamp(datetime.now().timestamp() - 90 * 86400).isoformat()
    for block in q4c_blocks:
        for node in ((block.get("graphSearch") or {}).get("nodes") or []):
            ents = node.get("entities") or []
            if len(ents) < 2:
                continue
            te, se = ents[0], ents[1]
            if te.get("type") != "TECHNOLOGY" or se.get("type") != "SERVICE_ACCOUNT":
                continue
            tn = te.get("name", "Unknown")
            ca = (se.get("properties") or {}).get("createdAt")
            if not ca:
                continue
            tech_dates.setdefault(tn, []).append(ca)

    per_tl = {}
    for name, dates in tech_dates.items():
        min_i = min(dates)
        max_i = max(dates)
        nc = len([d for d in dates if d > cutoff90d])
        per_tl[name] = {"first_added": fmt_dmy(min_i), "latest_add": fmt_dmy(max_i), "new_count": nc}

    techs = []
    for name, info in totals.items():
        props = info.get("properties") or {}
        cats = ", ".join(props.get("categories")) if isinstance(props.get("categories"), list) else str(props.get("categories") or "")
        last_seen = (props.get("lastSeenAt") or props.get("updatedAt") or "")[:10]
        tl = per_tl.get(name, {})
        techs.append({
            "name": name,
            "sa_count": info.get("count", 0),
            "sa_active": (actives.get(name) or {}).get("count", 0),
            "categories": cats,
            "tiers": classify_tiers(cats),
            "last_seen": last_seen,
            "first_added": tl.get("first_added", ""),
            "latest_add": tl.get("latest_add", ""),
            "new_count": tl.get("new_count", 0),
        })
    techs.sort(key=lambda t: t["sa_count"], reverse=True)

    t1 = [t for t in techs if "Tier 1" in t["tiers"]]
    t2 = [t for t in techs if "Tier 2 (Code)" in t["tiers"]]
    t3 = [t for t in techs if "Tier 3 (Sensor)" in t["tiers"]]
    oth = [t for t in techs if "Other" in t["tiers"]]

    def calc_pct(a, tot):
        return "0" if not tot else str(round((a / tot) * 100))

    def sum_sa(arr):
        return sum(x["sa_count"] for x in arr)

    def sum_ac(arr):
        return sum(x["sa_active"] for x in arr)

    out["PI_T1_COUNT"] = str(len(t1))
    out["PI_T1_SA"] = str(sum_sa(t1))
    out["PI_T1_AC"] = str(sum_ac(t1))
    out["PI_T1_PA"] = calc_pct(sum_ac(t1), sum_sa(t1))

    out["PI_T2_COUNT"] = str(len(t2))
    out["PI_T2_SA"] = str(sum_sa(t2))
    out["PI_T2_AC"] = str(sum_ac(t2))
    out["PI_T2_PA"] = calc_pct(sum_ac(t2), sum_sa(t2))

    out["PI_T3_COUNT"] = str(len(t3))
    out["PI_T3_SA"] = str(sum_sa(t3))
    out["PI_T3_AC"] = str(sum_ac(t3))
    out["PI_T3_PA"] = calc_pct(sum_ac(t3), sum_sa(t3))

    out["PI_OTH_COUNT"] = str(len(oth))
    out["PI_TOT"] = str(len(techs))
    out["PI_TOT_SA"] = str(sum_sa(techs))
    out["PI_TOT_AC"] = str(sum_ac(techs))
    out["PI_TOT_PA"] = calc_pct(sum_ac(techs), sum_sa(techs))

    def fill_slot(prefix, bucket, slot):
        idx = slot - 1
        if idx < len(bucket):
            b = bucket[idx]
            out[f"{prefix}_{slot}"] = b["name"]
            out[f"{prefix}_{slot}_SA"] = str(b["sa_count"])
            out[f"{prefix}_{slot}_AC"] = str(b["sa_active"])
            out[f"{prefix}_{slot}_PA"] = calc_pct(b["sa_active"], b["sa_count"])
            out[f"{prefix}_{slot}_CAT"] = b["categories"]
            out[f"{prefix}_{slot}_SEEN"] = b["last_seen"]
            out[f"{prefix}_{slot}_NC"] = str(b.get("new_count", 0))
            out[f"{prefix}_{slot}_FA"] = b.get("first_added", "")
            out[f"{prefix}_{slot}_LA"] = b.get("latest_add", "")
            out[f"{prefix}_{slot}_NF"] = "NEW" if b.get("new_count", 0) > 0 else ""
        else:
            for k in [f"{prefix}_{slot}", f"{prefix}_{slot}_SA", f"{prefix}_{slot}_AC", f"{prefix}_{slot}_PA", f"{prefix}_{slot}_CAT", f"{prefix}_{slot}_SEEN", f"{prefix}_{slot}_FA", f"{prefix}_{slot}_LA", f"{prefix}_{slot}_NF", f"{prefix}_{slot}_NC"]:
                out[k] = ""

    for s in range(1, 9):
        fill_slot("PI_T1", t1, s)
    for s in range(1, 6):
        fill_slot("PI_T2", t2, s)
    for s in range(1, 6):
        fill_slot("PI_T3", t3, s)

    has_t1 = len(t1) > 0
    has_t2 = len(t2) + len(t3) > 0
    out["PI_WARP_T1"] = "ALERT" if has_t1 else "CLEAR"
    out["PI_WARP_T2"] = "ALERT" if has_t2 else "CLEAR"
    out["PI_WARP_SENTIMENT"] = "RED" if has_t1 else "YELLOW" if has_t2 else "GREEN"
    out["PI_WARP_SLA"] = "2 business days" if has_t1 else "5 business days" if has_t2 else "N/A"

    def nt_count(arr):
        return len([t for t in arr if t.get("new_count", 0) > 0])

    def ns_sum(arr):
        return sum(t.get("new_count", 0) for t in arr)

    out["PI_TOT_NT"] = str(nt_count(techs))
    out["PI_TOT_NS"] = str(ns_sum(techs))
    out["PI_T1_NT"] = str(nt_count(t1))
    out["PI_T1_NS"] = str(ns_sum(t1))
    out["PI_T2_NT"] = str(nt_count(t2))
    out["PI_T2_NS"] = str(ns_sum(t2))
    out["PI_T3_NT"] = str(nt_count(t3))
    out["PI_T3_NS"] = str(ns_sum(t3))

    if q_shi.get("systemHealthIssues"):
        out["SHI_R_C"] = str(q_shi["systemHealthIssues"].get("criticalSeverityCount", 0))
        out["SHI_R_H"] = str(q_shi["systemHealthIssues"].get("highSeverityCount", 0))

    def sum_tfc(g):
        nodes = (g.get("nodes") if isinstance(g, dict) else []) or []
        return sum(((n.get("analytics") or {}).get("totalFindingCount", 0)) for n in nodes)

    ai_sf_c = (q_ai.get("aiSecurityFindingsCount") or q4b.get("aiSecurityFindingsCount") or {}).get("totalCount")
    ai_mf_c = (q_ai.get("cloudConfigFindingsCount") or q4b.get("cloudConfigFindingsCount") or {}).get("totalCount")
    ai_if_c = (q_ai.get("inventoryFindingsCount") or q4b.get("inventoryFindingsCount") or {}).get("totalCount")

    if ai_sf_c is not None:
        out["AI_SF"] = fmt_r(ai_sf_c)
    elif q_ai.get("aiSecFindings"):
        out["AI_SF"] = fmt_r(sum_tfc(q_ai["aiSecFindings"]))
    elif not out.get("AI_SF"):
        out["AI_SF"] = "0"

    if ai_mf_c is not None:
        out["AI_MF"] = fmt_r(ai_mf_c)
    elif q_ai.get("aiMisconfigFindings"):
        out["AI_MF"] = fmt_r(sum_tfc(q_ai["aiMisconfigFindings"]))
    elif not out.get("AI_MF"):
        out["AI_MF"] = "0"

    if ai_if_c is not None:
        out["AI_IF"] = fmt_r(ai_if_c)
    elif q_ai.get("aiImpactFindings"):
        out["AI_IF"] = fmt_r(sum_tfc(q_ai["aiImpactFindings"]))
    elif not out.get("AI_IF"):
        out["AI_IF"] = "0"

    # --- Slide 4: "Cloud Advanced" adoption breakdown ----------------------------
    # Model (confirmed with owner 2026-08-28): coverage % where a real coverage metric
    # exists, else enabled->100 / disabled->0 for pure feature toggles. Header L_CL_PCT
    # is the average of the eight items. Computed here (after all dependencies) rather
    # than the old hardcoded 0 stubs. UVM and SaaS Users use a best-effort mapping
    # (flagged for review) since there is no single canonical tenant signal for them.
    def _pct_int(s):
        try:
            return max(0, min(100, int(float(str(s).replace("%", "").strip()))))
        except (TypeError, ValueError):
            return None

    # Compute = workload scan success %; Data = DSPM coverage %
    cl_cp = _pct_int(out.get("WS_P"))
    cl_dp = _pct_int(out.get("DS_P"))

    # Non-OS / Registry / VM image = combined coverage across the three scan types
    _nrv_succ = (non_succ or 0) + (rci_succ or 0) + (vmi_succ or 0)
    _nrv_tot = (non_t or 0) + (rci_t or 0) + (vmi_t or 0)
    cl_nrvp = int(math.floor(_nrv_succ / _nrv_tot * 100)) if _nrv_tot > 0 else None

    # WizOS adoption = wizOS workloads / total compute workloads
    try:
        _wos = int(out.get("WIZOS_WORKLOAD_COUNT", "0") or 0)
        _cwt = int(out.get("COMPUTE_WL_TOTAL", "0") or 0)
        cl_wop = int(math.floor(_wos / _cwt * 100)) if _cwt > 0 else (0 if _wos == 0 else None)
    except (TypeError, ValueError):
        cl_wop = None

    # Advanced ASM / Red Agent = enabled -> 100 else 0 (pure feature toggles)
    cl_asmp = 100 if (adv.get("isEnabled") is True) else 0
    cl_reda = 100 if (red_agent_on is True) else 0

    # UVM (best-effort, REVIEW): fraction of vulnerability-assessment detection toggles on
    _uvm_flags = [
        vas.get("latestKernelVersionVulnerabilitiesDetectionEnabled"),
        vas.get("osPackageManagedCodeLibrariesVulnerabilitiesDetectionEnabled"),
        vas.get("windowsManagedVulnerabilitiesDetectionEnabled"),
        vas.get("goStandardLibraryVulnerabilitiesEnabled"),
        vas.get("pipInstalledPythonLibrariesVulnerabilitiesEnabled"),
        vas.get("npmInstalledJavascriptLibrariesVulnerabilitiesEnabled"),
    ]
    _uvm_known = [b for b in _uvm_flags if b is not None]
    cl_uvmp = int(math.floor(sum(1 for b in _uvm_known if b) / len(_uvm_known) * 100)) if _uvm_known else None

    # SaaS Users (best-effort, REVIEW): SaaS security scanner enabled -> 100 else 0
    cl_sup = 100 if str(out.get("ASM_SAAS", "")).strip().lower() in ("enabled", "yes", "true") else 0

    _cl_map = {
        "CL_CP": cl_cp, "CL_DP": cl_dp, "CL_NRVP": cl_nrvp, "CL_WOP": cl_wop,
        "CL_UVMP": cl_uvmp, "CL_ASMP": cl_asmp, "CL_REDA": cl_reda, "CL_SUP": cl_sup,
    }
    _cl_present = [v for v in _cl_map.values() if v is not None]
    for _k, _v in _cl_map.items():
        out[_k] = str(_v if _v is not None else 0)
    out["L_CL_PCT"] = f"{int(round(sum(_cl_present) / len(_cl_present)))}%" if _cl_present else "0%"

    return out


def process_raw_api_delta(text: str) -> Optional[Dict[str, Any]]:
    if not text or not text.strip():
        return None
    blocks = split_json_blocks(text)
    if len(blocks) < 2:
        return None
    c = classify_blocks(blocks)
    if not any([c["q1"], c["q2"], c["q3"], c["q4a"], c["q4b"], c["q4c"], c["q5"], c["qShi"], c["qAi"]]):
        return None
    return {
        "flat": run_post_process(c),
        "blocks_found": len(blocks),
        "q1_present": bool(c["q1"]),
        "q2_present": bool(c["q2"]),
        "q3_present": bool(c["q3"]),
        "q4a_present": bool(c["q4a"]),
        "q4b_present": bool(c["q4b"]),
        "q4c_present": bool(c["q4c"]),
        "q5_present": bool(c["q5"]),
        "qShi_present": bool(c["qShi"] and c["qShi"].get("systemHealthIssues")),
        "qAi_present": bool(c["qAi"]),
    }


def build_replacement_requests(
    customer_name: str,
    today_str: str,
    tam_metrics: Dict[str, Any],
    api_delta_text: str = "",
    preview_vars: Optional[Dict[str, Any]] = None,
    pre: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Merges BQ metrics, API delta, preview hub vars, and derived fields.
    Returns:
      (slides_requests_list, merged_variables_map)
    """
    pre = pre or {}
    preview_vars = preview_vars or {}
    merged = {}

    # 1. Base BigQuery metrics
    for k, v in tam_metrics.items():
        if k.startswith("_"):
            continue
        merged[k] = {"variable": k, "value": str(v if v is not None else ""), "source": "BQ"}

    # 2. API Delta overrides
    api_result = process_raw_api_delta(api_delta_text)
    if api_result:
        for k, v in api_result["flat"].items():
            merged[k] = {"variable": k, "value": str(v if v is not None else ""), "source": "API"}

        if api_result["flat"].get("WIZOS_WORKLOAD_COUNT") is not None:
            merged["CON_WOS"] = {"variable": "CON_WOS", "value": str(api_result["flat"]["WIZOS_WORKLOAD_COUNT"]), "source": "API"}

    # 3. Derived metrics: WS_P, DS_P
    def pct_from_total(tk, fk, ok):
        if ok in merged:
            return
        te = merged.get(tk)
        fe = merged.get(fk)
        if not te or not fe:
            return
        try:
            t = float(str(te["value"]).replace(",", ""))
            f = float(str(fe["value"]).replace(",", ""))
            if t > 0:
                merged[ok] = {"variable": ok, "value": f"{(f / t * 100):.1f}%", "source": te["source"]}
        except Exception:
            pass

    pct_from_total("WS_T", "WS_F", "WS_P")
    pct_from_total("DS_T", "DS_F", "DS_P")

    # 4. L_CL_PCT
    lcl_entry = merged.get("L_CL")
    if lcl_entry and lcl_entry["value"] != "N/A":
        lcl_parts = str(lcl_entry["value"]).split("/")
        if len(lcl_parts) == 2:
            def parse_suffixed(s):
                t = s.strip().replace(",", "")
                if t.endswith("B"):
                    return float(t[:-1]) * 1e9
                if t.endswith("M"):
                    return float(t[:-1]) * 1e6
                if t.endswith("K"):
                    return float(t[:-1]) * 1e3
                if t in ("∞", "Infinity"):
                    return float("inf")
                return float(t)
            try:
                lcl_used = parse_suffixed(lcl_parts[0])
                lcl_total = parse_suffixed(lcl_parts[1])
                if lcl_total > 0 and lcl_total != float("inf"):
                    merged["L_CL_PCT"] = {"variable": "L_CL_PCT", "value": f"{round(lcl_used / lcl_total * 100)}%", "source": "calculated"}
            except Exception:
                pass

    # 5. ASM billable workload units
    try:
        ae_http = float(re.sub(r"[^0-9.]", "", str((merged.get("AE_HTTP") or {}).get("value", 0))))
    except ValueError:
        ae_http = 0.0
    try:
        ae_nhttp = float(re.sub(r"[^0-9.]", "", str((merged.get("AE_NHTTP") or {}).get("value", 0))))
    except ValueError:
        ae_nhttp = 0.0
    try:
        ae_tot = float(re.sub(r"[^0-9.]", "", str((merged.get("AE_TOT") or {}).get("value", 0))))
    except ValueError:
        ae_tot = 0.0

    ae_wtot = round((ae_http / 25.0) + (ae_nhttp / 50.0))
    if (ae_http + ae_nhttp) > 0:
        merged["AE_TOT"] = {"variable": "AE_TOT", "value": str(ae_wtot), "source": "calculated"}
        merged["AE_WTOT"] = {"variable": "AE_WTOT", "value": str(ae_wtot), "source": "calculated"}

    # 6. Customer & Date metadata
    merged["Customer"] = {"variable": "Customer", "value": str(customer_name), "source": "input"}
    if today_str:
        tp = today_str.split("-")
        today_fmt = f"{tp[1]}/{tp[2]}/{tp[0]}" if len(tp) == 3 else today_str
        merged["TODAY"] = {"variable": "TODAY", "value": today_fmt, "source": "calculated"}

    # Contract & Tenure calculations (Prioritize pre/BQ, fallback to live API tenant info)
    now_dt = datetime.strptime(today_str[:10], "%Y-%m-%d")
    flat_api = api_result.get("flat", {}) if api_result else {}
    
    # 1. Days until renewal & Contract End
    if pre.get("days_until_renewal") is not None:
        merged["D_U_R"] = {"variable": "D_U_R", "value": str(pre["days_until_renewal"]), "source": "BQ"}
    elif flat_api.get("D_U_R"):
        merged["D_U_R"] = {"variable": "D_U_R", "value": str(flat_api["D_U_R"]), "source": "API"}

    if pre.get("renewal_date") is not None:
        merged["RENEWAL_DATE"] = {"variable": "RENEWAL_DATE", "value": str(pre["renewal_date"]), "source": "BQ"}
    elif flat_api.get("RENEWAL_DATE"):
        merged["RENEWAL_DATE"] = {"variable": "RENEWAL_DATE", "value": str(flat_api["RENEWAL_DATE"]), "source": "API"}

    if pre.get("renewal_date"):
        try:
            rd_raw = str(pre["renewal_date"])[:10]
            rd_parts = rd_raw.split("-")
            rd_fmt = f"{rd_parts[1]}/{rd_parts[2]}/{rd_parts[0]}" if len(rd_parts) == 3 else rd_raw
            merged["CONTRACT_END_FMT"] = {"variable": "CONTRACT_END_FMT", "value": rd_fmt, "source": "calculated"}
        except Exception:
            pass
    elif flat_api.get("CONTRACT_END_FMT"):
        merged["CONTRACT_END_FMT"] = {"variable": "CONTRACT_END_FMT", "value": str(flat_api["CONTRACT_END_FMT"]), "source": "API"}

    # 2. Customer tenure (Days as Wiz customer)
    if pre.get("customer_since"):
        try:
            cs_date = datetime.strptime(str(pre["customer_since"])[:10], "%Y-%m-%d")
            diff_days = (now_dt - cs_date).days
            merged["CUS_NOD"] = {"variable": "CUS_NOD", "value": str(diff_days), "source": "calculated"}
        except Exception:
            merged["CUS_NOD"] = {"variable": "CUS_NOD", "value": "N/A", "source": "calculated"}
    elif flat_api.get("CUS_NOD"):
        merged["CUS_NOD"] = {"variable": "CUS_NOD", "value": str(flat_api["CUS_NOD"]), "source": "API"}

    # 7. Preview Hub Variables
    for pk, pv in preview_vars.items():
        merged[pk] = {"variable": pk, "value": str(pv if pv is not None else ""), "source": "preview_hub"}

    # 8. Build Slides replaceAllText requests
    requests = []

    # Clean up empty PI date pairs before individual token replacements
    for prefix in ["PI_T1", "PI_T2", "PI_T3"]:
        for s in range(1, 9):
            fa_val = (merged.get(f"{prefix}_{s}_FA") or {}).get("value", "")
            la_val = (merged.get(f"{prefix}_{s}_LA") or {}).get("value", "")
            if not fa_val and not la_val:
                p1 = "{{" + f"{prefix}_{s}_FA" + "}} / {{" + f"{prefix}_{s}_LA" + "}}"
                p2 = "{{" + f"{prefix}_{s}_FA" + " / " + f"{prefix}_{s}_LA" + "}}"
                p3 = "{{" + f"{prefix}_{s}_FA" + "}}/{{" + f"{prefix}_{s}_LA" + "}}"
                for pat in [p1, p2, p3]:
                    requests.append({"replaceAllText": {"containsText": {"text": pat, "matchCase": True}, "replaceText": ""}})
    for var_name, data in merged.items():
        if var_name.startswith("__DIAG_"):
            continue
        val = apply_fmt(var_name, data["value"])
        token_str = "{{" + var_name + "}}"
        requests.append({"replaceAllText": {"containsText": {"text": token_str, "matchCase": True}, "replaceText": val}})
        
        # Handle template whitespace variations (e.g. {{ASM_ RECON }}, {{VS_ LVULN }})
        if var_name.startswith("ASM_"):
            sub = var_name[4:]
            for pat in [f"{{{{ASM_\n{sub}\n}}}}", f"{{{{ASM_ {sub} }}}}", f"{{{{ASM_{sub} }}}}", f"{{{{ASM_ {sub}}}}}"]:
                requests.append({"replaceAllText": {"containsText": {"text": pat, "matchCase": True}, "replaceText": val}})
        elif var_name.startswith("VS_"):
            sub = var_name[3:]
            for pat in [f"{{{{VS_\n{sub}\n}}}}", f"{{{{VS_ {sub} }}}}", f"{{{{VS_{sub} }}}}", f"{{{{VS_ {sub}}}}}"]:
                requests.append({"replaceAllText": {"containsText": {"text": pat, "matchCase": True}, "replaceText": val}})
        
        if var_name == "IMGS":
            requests.append({"replaceAllText": {"containsText": {"text": "{{TI}}", "matchCase": True}, "replaceText": val}})

    # 9. Best Practice evaluated icons
    for var_name, rec_val in RECS.items():
        entry = merged.get(var_name)
        val = apply_fmt(var_name, entry["value"]) if entry else ""
        status = eval_config(val, rec_val)
        rec_token_str = "{{" + var_name + "_R}}"
        requests.append({"replaceAllText": {"containsText": {"text": rec_token_str, "matchCase": True}, "replaceText": BP[status]}})
        merged[f"{var_name}_R"] = {"variable": f"{var_name}_R", "value": BP[status], "source": "calculated"}
        if var_name == "ASM_SAAS":
            # Typo in master template on Slide 19
            requests.append({"replaceAllText": {"containsText": {"text": "{{ASM_SASS_R}}", "matchCase": True}, "replaceText": BP[status]}})
            merged["ASM_SASS_R"] = {"variable": "ASM_SASS_R", "value": BP[status], "source": "calculated"}

    # 10. QBR slide 1 single-brace date
    if today_str:
        tp = today_str.split("-")
        dt_fmt = f"{tp[1]}/{tp[2]}/{tp[0]}" if len(tp) == 3 else today_str
        requests.append({"replaceAllText": {"containsText": {"text": "{Date}", "matchCase": True}, "replaceText": dt_fmt}})

    return requests, merged
