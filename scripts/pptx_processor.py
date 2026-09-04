"""
Local PowerPoint (.pptx) Template Processor for Wiz Health Assessment.
=======================================================================
Replaces template tokens {{VARIABLE}} across all slides in a .pptx presentation,
handles multiline bullet expansions, highlights enabled preview features in soft green,
cleans up empty date pairs, and sweeps unfilled tokens without requiring external Office APIs.
"""

import copy
import datetime
import os
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
}

# Namespaces used only inside extension lists (extLst). ElementTree reserializes any
# namespace it doesn't know with a generated prefix (ns0, ns3, ...) and drops the
# inline xmlns declaration, which corrupts these Microsoft extensions on every slide
# we round-trip. In particular `ahyp:hlinkClr` (hyperlink color) getting rewritten as
# `ns3:hlinkClr` makes some lenient renderers paint those links black instead of the deck's link
# color — but only on slides that contain a {{token}} (the ones we actually modify),
# which is exactly the "some links are black" symptom. Register them so prefixes and
# declarations survive the round-trip.
EXT_NS = {
    "ahyp": "http://schemas.microsoft.com/office/drawing/2018/hyperlinkcolor",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "a14": "http://schemas.microsoft.com/office/drawing/2010/main",
    "a16": "http://schemas.microsoft.com/office/drawing/2014/main",
    "p14": "http://schemas.microsoft.com/office/powerpoint/2010/main",
}

# Register namespaces so ET doesn't mangle tags/prefixes when writing back XML
for prefix, uri in {**NS, **EXT_NS}.items():
    ET.register_namespace(prefix, uri)


# --- Status-mark normalization (green check / red X) --------------------------
# The deck's status marks use color emoji (✅ U+2705 / ❌ U+274C) and dingbats set
# in font "Calibri", which lacks those glyphs and is NOT embedded in the deck — so
# on a viewer whose font fallback doesn't cover them (seen on some customer
# machines) the marks silently vanish. We rewrite every mark to ✓ (U+2713) / ✗
# (U+2717) in "JetBrains Mono", which IS embedded in this deck and contains both
# glyphs, so the marks travel with the .pptx and render in PowerPoint, Google
# renderers alike. Surrounding text in the same run keeps its font.
_MARK_FONT = "JetBrains Mono"
_MARK_MAP = {"✅": "✓", "✓": "✓", "✔": "✓", "❌": "✗", "✗": "✗", "✘": "✗"}
_MARK_CHECK_SRC = set("✅✓✔")
_MARK_GREEN = "218C21"
_MARK_RED = "CC1212"


def normalize_status_marks(slide_xml: str) -> str:
    """Rewrite runs containing check/X marks so each mark glyph uses an embedded
    font that actually has it. Runs with no marks are returned unchanged."""

    def rebuild(m):
        run = m.group(0)
        tm = re.search(r"<a:t>([^<]*)</a:t>", run)
        if not tm:
            return run
        text = tm.group(1)
        if not any(c in _MARK_MAP for c in text):
            return run
        rpr_m = re.search(r"<a:rPr\b.*?</a:rPr>|<a:rPr\b[^>]*/>", run, re.S)
        rpr = rpr_m.group(0) if rpr_m else "<a:rPr/>"

        segs, cur, cur_mark = [], "", None
        for ch in text:
            is_mark = ch in _MARK_MAP
            if cur and is_mark != cur_mark:
                segs.append((cur, cur_mark))
                cur = ""
            cur += ch
            cur_mark = is_mark
        if cur:
            segs.append((cur, cur_mark))

        out = []
        for seg, is_mark in segs:
            if not is_mark:
                out.append(f"<a:r>{rpr}<a:t>{seg}</a:t></a:r>")
                continue
            new_text = "".join(_MARK_MAP[c] for c in seg)
            color = _MARK_GREEN if seg[0] in _MARK_CHECK_SRC else _MARK_RED
            r = rpr
            for tag in ("latin", "cs", "ea", "sym"):
                r = re.sub(rf'(<a:{tag} typeface=")[^"]*(")', rf"\g<1>{_MARK_FONT}\g<2>", r)
            if "<a:latin " not in r and "<a:rPr" in r and not r.endswith("/>"):
                r = re.sub(r"(<a:rPr\b[^>]*>)", rf'\1<a:latin typeface="{_MARK_FONT}"/>', r, count=1)
            if "<a:solidFill>" in r:
                r = re.sub(r'(<a:solidFill><a:srgbClr val=")[0-9A-Fa-f]{6}(")', rf"\g<1>{color}\g<2>", r, count=1)
            elif "<a:rPr" in r and not r.endswith("/>"):
                r = re.sub(r"(<a:rPr\b[^>]*>)", rf'\1<a:solidFill><a:srgbClr val="{color}"/></a:solidFill>', r, count=1)
            out.append(f"<a:r>{r}<a:t>{new_text}</a:t></a:r>")
        return "".join(out)

    return re.sub(r"<a:r>.*?</a:r>", rebuild, slide_xml, flags=re.S)


# --- Split-token normalization ------------------------------------------------
# PowerPoint's editor routinely splits a {{TOKEN}} across several runs on save
# (e.g. {{WS_F}} becomes three runs: ': {{WS_' / 'F' / '}}'). When that happens the
# token-replacement path below can't reproduce the paragraph run-by-run, so it falls
# back to dumping the whole replaced paragraph into the FIRST run. If that first run
# is a differently-formatted label — e.g. a hyperlinked heading like "Failed Workload
# Scans" — the value inherits the wrong formatting (the "linked {{WS_F}}" bug that
# keeps coming back every time the template is re-saved).
#
# This pre-pass runs on the raw slide XML BEFORE parsing and merges any run sequence
# that a split spread a token across back into a single run, using the rPr of the run
# where '{{' begins (the token's own run) — so sibling label runs keep their own
# formatting and the value renders clean. It only merges runs that are directly
# adjacent (no <a:br/> or other element between them), so line breaks are preserved.
_SPLIT_RUN_RE = re.compile(r"<a:r>(?P<body>.*?)<a:t>(?P<text>[^<]*)</a:t></a:r>", re.S)


def normalize_split_tokens(slide_xml: str) -> str:
    """Merge adjacent runs that a PowerPoint edit split a ``{{TOKEN}}`` across, so each
    token lives in a single run again. Idempotent; a slide with no split tokens is
    returned unchanged."""
    changed = True
    while changed:
        changed = False
        runs = list(_SPLIT_RUN_RE.finditer(slide_xml))
        for i, m in enumerate(runs):
            text = m.group("text")
            # A token whose '{{' is open but not closed within this run is split.
            if "{{" in text and "}}" not in text.split("{{", 1)[1]:
                if i + 1 < len(runs):
                    nxt = runs[i + 1]
                    # Only merge truly-adjacent runs (nothing but whitespace between
                    # them) so we never swallow an <a:br/>, <a:fld/>, etc.
                    if slide_xml[m.end():nxt.start()].strip() == "":
                        merged = ("<a:r>" + m.group("body") + "<a:t>"
                                  + text + nxt.group("text") + "</a:t></a:r>")
                        slide_xml = slide_xml[:m.start()] + merged + slide_xml[nxt.end():]
                        changed = True
                        break
    return slide_xml


def process_pptx_template(
    template_path: str,
    output_path: str,
    variables: Dict[str, Any],
    enabled_preview_titles: Optional[Set[str]] = None
) -> Dict[str, Any]:
    """
    Process a master .pptx template:
    1. Replaces all {{KEY}} tokens with their corresponding values.
    2. Expands multiline variables into distinct paragraphs preserving typography.
    3. Cleans up empty PI date pairs (e.g. ' / ').
    4. Highlights enabled preview features on preview slides.
    5. Sweeps any remaining unfilled {{...}} tokens across run boundaries.
    """
    template_file = Path(template_path)
    if not template_file.is_file():
        raise FileNotFoundError(f"PPTX template not found at: {template_path}")

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Flatten variable values to string
    var_dict = {}
    for k, v in variables.items():
        if isinstance(v, dict) and "value" in v:
            var_dict[k] = str(v["value"] if v["value"] is not None else "")
        else:
            var_dict[k] = str(v if v is not None else "")

    # Pre-clean empty PI date pairs
    for prefix in ["PI_T1", "PI_T2", "PI_T3"]:
        for s in range(1, 9):
            fa_val = var_dict.get(f"{prefix}_{s}_FA", "")
            la_val = var_dict.get(f"{prefix}_{s}_LA", "")
            if not fa_val and not la_val:
                var_dict[f"{prefix}_{s}_FA"] = ""
                var_dict[f"{prefix}_{s}_LA"] = ""

    # Ensure date fallback
    today_str = datetime.datetime.now().strftime("%B %d, %Y")
    if not var_dict.get("DATE"):
        var_dict["DATE"] = today_str

    enabled_titles = {t.strip().lower() for t in (enabled_preview_titles or set())}
    replacements_made = 0
    highlighted_count = 0
    swept_tokens = 0

    cust_name = var_dict.get("CUSTOMER", "custom")

    def apply_run_repl(s: str) -> str:
        """Apply the same token substitutions as the flatten path, but to a
        SINGLE run's text so run boundaries and <a:br/> line breaks survive.
        Cross-run cleanups (empty date-pair slashes, unknown-token sweep) are
        intentionally omitted here; if they would change the text, the caller
        detects the mismatch against the flattened result and falls back to the
        old single-run write."""
        if "{Date}" in s:
            s = s.replace("{Date}", today_str)
        if "{date}" in s:
            s = s.replace("{date}", today_str)
        if "for{{" in s:
            s = re.sub(r"for\{\{", "for {{", s)
        for k, v in var_dict.items():
            tok = "{{" + k + "}}"
            if tok in s:
                s = s.replace(tok, v)
        if "custom TWDC Graph Controls" in s:
            s = s.replace("custom TWDC Graph Controls", f"{cust_name} custom Graph Controls")
        for idx in (1, 2, 3):
            if var_dict.get(f"CI_CBC_{idx}") == "":
                s = s.replace(f"{{{{CI_CBC_{idx}}}}} Issues", "").replace(f"{{{{CI_CBC_{idx}}}}}", "")
        s = re.sub(r"%{2,}", "", s)
        return s

    with zipfile.ZipFile(template_file, "r") as zin, zipfile.ZipFile(output_file, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            content = zin.read(item.filename)

            if item.filename.startswith("ppt/slides/slide") and item.filename.endswith(".xml"):
                # Pre-pass: re-join any {{TOKEN}} that a PowerPoint save split across
                # runs, so replacement keeps each run's own formatting (prevents the
                # value inheriting a sibling label's hyperlink — the "linked WS_F" bug).
                _raw = content.decode("utf-8")
                _joined = normalize_split_tokens(_raw)
                if _joined != _raw:
                    content = _joined.encode("utf-8")

                root = ET.fromstring(content)
                slide_modified = False

                # Build parent map for inserting expanded multiline paragraphs
                parent_map = {c: p for p in root.iter() for c in p}

                def para_text_break_aware(para):
                    """Concatenate a paragraph's run text, turning <a:br/> line
                    breaks into '\\n' so labels-above-values and other multi-line
                    layouts survive token expansion (a plain join of <a:t> would
                    glue 'Advanced License:' to the first bullet of its value)."""
                    parts = []
                    for child in list(para):
                        tag = child.tag.split("}")[-1]
                        if tag in ("r", "fld"):
                            te = child.find("a:t", NS)
                            if te is not None and te.text:
                                parts.append(te.text)
                        elif tag == "br":
                            parts.append("\n")
                    return "".join(parts)

                paragraphs = list(root.findall(".//a:p", NS))
                for p in paragraphs:
                    t_elems = p.findall(".//a:t", NS)
                    if not t_elems:
                        continue

                    full_text = para_text_break_aware(p)
                    if "{{" not in full_text and "{Date}" not in full_text and "{date}" not in full_text:
                        continue

                    replaced_text = full_text

                    # Handle special single-curly date placeholders
                    if "{Date}" in replaced_text:
                        replaced_text = replaced_text.replace("{Date}", today_str)
                    if "{date}" in replaced_text:
                        replaced_text = replaced_text.replace("{date}", today_str)

                    # Handle spacing if "for{{CUSTOMER}}"
                    if "for{{" in replaced_text:
                        replaced_text = re.sub(r"for\{\{", "for {{", replaced_text)

                    has_multiline = False

                    for k, v in var_dict.items():
                        tok = "{{" + k + "}}"
                        if tok in replaced_text:
                            if "\n" in v:
                                has_multiline = True
                            replaced_text = replaced_text.replace(tok, v)
                            replacements_made += 1

                    # Clean up hardcoded customer text on Slide 12
                    if "custom TWDC Graph Controls" in replaced_text:
                        cust = var_dict.get("CUSTOMER", "custom")
                        replaced_text = replaced_text.replace("custom TWDC Graph Controls", f"{cust} custom Graph Controls")

                    # Clean up empty CI_CBC Issue labels when 0 critical controls
                    for idx in [1, 2, 3]:
                        if var_dict.get(f"CI_CBC_{idx}") == "":
                            replaced_text = replaced_text.replace(f"{{{{CI_CBC_{idx}}}}} Issues", "").replace(f"{{{{CI_CBC_{idx}}}}}", "")

                    # Clean up empty date pair slashes
                    replaced_text = re.sub(r"\{\{[^}]+\}\}\s*/\s*\{\{[^}]+\}\}", "", replaced_text)
                    replaced_text = re.sub(r"\{\{[^}]+\s*/\s*[^}]+\}\}", "", replaced_text)
                    
                    # Clean up dangling %%%%%% artifacts
                    replaced_text = re.sub(r"%{2,}", "", replaced_text)

                    # Sweep any remaining unfilled tokens in this paragraph
                    remaining_in_p = re.findall(r"\{\{[^}]+\}\}", replaced_text)
                    if remaining_in_p:
                        swept_tokens += len(remaining_in_p)
                        replaced_text = re.sub(r"\{\{[^}]+\}\}", "", replaced_text)

                    if replaced_text != full_text:
                        slide_modified = True
                        parent_tx = parent_map.get(p)
                        if has_multiline and "\n" in replaced_text and parent_tx is not None:
                            # Multiline expansion: one paragraph -> one paragraph per
                            # line, each line KEEPING THE FORMATTING OF THE RUN IT
                            # CAME FROM. Naively cloning run 0 for every line gives
                            # value bullets the header run's size/weight (e.g. 11pt
                            # bold instead of the template's 9pt), which is exactly
                            # the "different sizes" artifact. So we walk the runs and
                            # breaks in order and pair each output line with its
                            # source run, then clone THAT run to preserve its rPr.
                            A = "http://schemas.openxmlformats.org/drawingml/2006/main"
                            # Walk runs and <a:br/> in order, building one (text,
                            # source_run) per line. Each <a:br/> ends a line; two
                            # consecutive breaks yield an INTENTIONAL blank line
                            # (e.g. the spacer the template puts between the Advanced
                            # and Sensor license sections) which must be preserved.
                            lines = []
                            cur_text = ""
                            cur_run = None
                            fallback_run = None
                            for child in list(p):
                                tag = child.tag.split("}")[-1]
                                if tag == "br":
                                    lines.append((cur_text, cur_run or fallback_run))
                                    cur_text = ""
                                    cur_run = None
                                elif tag in ("r", "fld"):
                                    te = child.find("a:t", NS)
                                    if fallback_run is None:
                                        fallback_run = child
                                    txt = apply_run_repl(te.text or "") if te is not None else ""
                                    segs = txt.split("\n")
                                    cur_text += segs[0]
                                    if cur_run is None:
                                        cur_run = child
                                    for extra in segs[1:]:
                                        lines.append((cur_text, cur_run or fallback_run))
                                        cur_text = extra
                                        cur_run = child
                            lines.append((cur_text, cur_run or fallback_run))
                            # Keep interior blank lines (intentional spacing) but
                            # trim trailing empties so we don't pad the box bottom.
                            while lines and lines[-1][0].strip() == "":
                                lines.pop()
                            p_index = list(parent_tx).index(p)
                            for i, (line, src_run) in enumerate(lines):
                                p_clone = copy.deepcopy(p)
                                # Keep pPr (bullet + paragraph props); drop all runs,
                                # breaks and fields, then append ONE run cloned from
                                # the source run so its size/weight/color survive.
                                for child in list(p_clone):
                                    if child.tag.split("}")[-1] in ("r", "br", "fld"):
                                        p_clone.remove(child)
                                if src_run is not None:
                                    new_run = copy.deepcopy(src_run)
                                else:
                                    new_run = ET.Element(f"{{{A}}}r")
                                te = new_run.find("a:t", NS)
                                if te is None:
                                    te = ET.SubElement(new_run, f"{{{A}}}t")
                                te.text = line
                                # OOXML CT_TextParagraph order is: pPr?, (r|br|fld)*,
                                # endParaRPr?. The cloned paragraph still carries the
                                # template's endParaRPr, so appending the run lands it
                                # AFTER endParaRPr -> PowerPoint drops the run and the
                                # line renders EMPTY (lenient renderers tolerate it).
                                # Insert the run BEFORE any
                                # endParaRPr so it stays the paragraph's last child.
                                _epr = p_clone.find("a:endParaRPr", NS)
                                if _epr is not None:
                                    p_clone.insert(list(p_clone).index(_epr), new_run)
                                else:
                                    p_clone.append(new_run)

                                # Soft green highlight for enabled preview features.
                                clean_line_title = line.lstrip("• ").split(" [")[0].strip().lower()
                                if clean_line_title and clean_line_title in enabled_titles:
                                    rPr = new_run.find("a:rPr", NS)
                                    if rPr is None:
                                        rPr = ET.Element(f"{{{A}}}rPr")
                                        new_run.insert(0, rPr)
                                    if rPr.find("a:highlight", NS) is None:
                                        hl = ET.Element(f"{{{A}}}highlight")
                                        srgb = ET.SubElement(hl, f"{{{A}}}srgbClr")
                                        srgb.set("val", "E0F5E0")
                                        # OOXML CT_TextCharacterProperties requires a strict
                                        # child order: highlight MUST precede latin/ea/cs/sym/
                                        # underline/hlink. Appending it (SubElement) puts it last,
                                        # which PowerPoint rejects -> the run renders EMPTY
                                        # (lenient renderers tolerate it). Insert before the first
                                        # element that must come after highlight.
                                        _after = {"latin", "ea", "cs", "sym", "uLnTx", "uLn",
                                                  "uFillTx", "uFill", "hlinkClick",
                                                  "hlinkMouseOver", "rtl", "extLst"}
                                        idx = len(list(rPr))
                                        for _j, _child in enumerate(list(rPr)):
                                            if _child.tag.split("}")[-1] in _after:
                                                idx = _j
                                                break
                                        rPr.insert(idx, hl)
                                        highlighted_count += 1

                                parent_tx.insert(p_index + i, p_clone)
                            parent_tx.remove(p)
                        else:
                            # Structure-preserving path: replace tokens within
                            # each run so <a:br/> line breaks and separately
                            # formatted runs (colored HIGH/CRITICAL badges,
                            # "Enabled" above its value) are kept instead of
                            # collapsing everything into the first run.
                            per_run = [apply_run_repl(t.text or "") for t in t_elems]
                            # replaced_text carries '\n' for <a:br/> breaks, which
                            # live as separate elements (not in run text), so strip
                            # them for the equality check against the run join.
                            if "".join(per_run) == replaced_text.replace("\n", ""):
                                for t, s in zip(t_elems, per_run):
                                    t.text = s
                            else:
                                # Cross-run token or cleanup the per-run pass
                                # can't reproduce (split token, date-pair slash):
                                # fall back to the flattened single-run write.
                                t_elems[0].text = replaced_text.replace("\n", "")
                                for other in t_elems[1:]:
                                    other.text = ""

                # Global sweep fallback across any straggler tokens
                for t in root.findall(".//a:t", NS):
                    if t.text and "{{" in t.text:
                        swept_count_in_text = len(re.findall(r"\{\{[^}]+\}\}", t.text))
                        if swept_count_in_text > 0:
                            swept_tokens += swept_count_in_text
                            t.text = re.sub(r"\{\{[^}]+\}\}", "", t.text)
                            slide_modified = True

                if slide_modified:
                    content = ET.tostring(root, encoding="utf-8")

                # Normalize status marks on EVERY slide (even ones with no tokens,
                # e.g. the scanner-config tables) so the green check / red X glyphs
                # use an embedded font and never vanish on the customer's viewer.
                _txt = content.decode("utf-8")
                _ntxt = normalize_status_marks(_txt)
                if _ntxt != _txt:
                    content = _ntxt.encode("utf-8")

            zout.writestr(item, content)

    return {
        "output_path": str(output_file),
        "file_size": os.path.getsize(output_file),
        "replacements_made": replacements_made,
        "highlighted_count": highlighted_count,
        "swept_tokens": swept_tokens
    }
