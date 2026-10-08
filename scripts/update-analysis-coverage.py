#!/usr/bin/env python3
"""Reconcile recorded coverage; never infer complete semantics from code exports.

Default: python scripts/update-analysis-coverage.py
Tests:   python scripts/update-analysis-coverage.py --self-test
One-time baseline import: --import-baseline OLD/work/trainer/audit
Snapshot the new resource research: --import-resources artifacts/next-research/drive-resource-content
The default run uses only repository inputs and the imported, hash-bound snapshots.
No imported Python, C#, IDA, archive member or game code is executed.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import copy
import hashlib
import html
import json
from pathlib import Path
import re
import struct
import zipfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/research/coverage"
BASE = 0x140000000
TARGET_SHA = "9002b2de6a1f91a790bd0673de125d1cf833f7942bfec827cdcf6ba64d5849ed"
SUMMARY_SHA = "4a24e4ac31e4e6d2be12561748868977d07b5d3877e08e087bd3d30021da5f7b"
SOURCE_SHA = "35e3cb99435e447af21c321799ad8d50145372827410d9f11bd5eb21289c2d5d"
BASELINE_NAMES = ("summary.json", "function_status.jsonl", "coverage.json")
DEFAULT_BINARY = Path(r"E:\SteamLibrary\steamapps\common\KINGDOM HEARTS -HD 1.5+2.5 ReMIX-\KINGDOM HEARTS II FINAL MIX.exe")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path, rows):
    path.write_text("".join(json.dumps(x, ensure_ascii=False, separators=(",", ":")) + "\n" for x in rows), encoding="utf-8")


def relative(path):
    return path.resolve().relative_to(ROOT).as_posix()


def address(value):
    # Address strings in IDA evidence are hexadecimal, including unprefixed ones.
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, str) and re.fullmatch(r"(?:0x)?[0-9a-fA-F]+", value.strip()):
        return int(value.strip(), 16)
    return None


def va(value):
    n = address(value)
    return None if n is None else (BASE + n if n < BASE else n)


def hx(value):
    return f"0x{value:x}" if value is not None else None


def nonnegative_int(value):
    return type(value) is int and value >= 0


def canonical_member(name):
    return isinstance(name, str) and bool(name) and not name.startswith("/") and "\\" not in name and ":" not in name and all(p not in ("", ".", "..") for p in name.split("/"))


def archive_inventory(path, expected_sha):
    data = path.read_bytes()
    if digest(data) != expected_sha:
        raise ValueError(f"Immutable archive hash mismatch: {path}")
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if any(not canonical_member(n.rstrip("/")) for n in names) or len({n.casefold() for n in names}) != len(names):
            raise ValueError("Archive has unsafe or duplicate paths")
    return set(names)


def import_baseline(folder):
    blobs = {n: (folder / n).read_bytes() for n in BASELINE_NAMES}
    if digest(blobs["summary.json"]) != SUMMARY_SHA:
        raise ValueError("Old full audit does not match the frozen v0.11 summary")
    summary = json.loads(blobs["summary.json"])
    coverage = json.loads(blobs["coverage.json"])
    rows = [json.loads(line) for line in blobs["function_status.jsonl"].splitlines() if line.strip()]
    if rows != coverage["functions"] or summary["counts"] != coverage["counts"] or summary["generated_utc"] != coverage["generated_utc"]:
        raise ValueError("Full-audit records do not agree with the matching summary")
    archive = OUT / "baseline-v011-full-audit.zip"
    if archive.exists():
        with zipfile.ZipFile(archive) as z:
            if any(z.read(n) != blobs[n] for n in BASELINE_NAMES):
                raise ValueError("Refusing to replace an existing baseline with different bytes")
    else:
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for n in BASELINE_NAMES:
                info = zipfile.ZipInfo(n, (1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(info, blobs[n], compresslevel=9)
    write_json(OUT / "baseline-provenance.json", {
        "schema": 1,
        "archive": relative(archive), "sha256": digest(archive.read_bytes()),
        "members": {n: {"bytes": len(b), "sha256": digest(b)} for n, b in blobs.items()},
        "originalImportDirectory": str(folder.resolve()),
        "matchingSummary": "docs/legacy/audit-summary-v011.json", "matchingSummarySha256": SUMMARY_SHA,
        "legacySourceArchive": "docs/legacy/KH2_Trainer_v0.11_Source.zip", "legacySourceArchiveSha256": SOURCE_SHA,
        "reason": "The immutable v0.11 Source.zip omits the full audit and its per-function records. Imported exact records from the older workspace only after its summary matched the frozen summary byte-for-byte and its function/status/count records agreed internally. Default regeneration uses this portable snapshot, not the old workspace.",
        "trust": "Historical recorded audit, not a new verification of all exports, claims, ASM or runtime behavior."
    })


def import_resources(folder):
    dest = OUT / "imported/drive-resource-content"
    dest.mkdir(parents=True, exist_ok=True)
    members = {}
    for name in ("evidence.json", "findings.json", "verification.json", "next_guard_tests.json"):
        path = folder / name
        if not path.is_file():
            raise ValueError(f"Missing resource research input {path}")
        data = path.read_bytes()
        json.loads(data)
        (dest / name).write_bytes(data)
        members[name] = {"bytes": len(data), "sha256": digest(data)}
    write_json(OUT / "resource-import-provenance.json", {"schema": 1, "sourceDirectory": str(folder.resolve()), "snapshotDirectory": relative(dest), "members": members, "scope": "Immutable evidence snapshot for this coverage run; code-range callbacks are not added to the native function inventory."})


def load_baseline():
    provenance = read_json(OUT / "baseline-provenance.json")
    archive = ROOT / provenance["archive"]
    archive_inventory(archive, provenance["sha256"])
    with zipfile.ZipFile(archive) as z:
        blobs = {n: z.read(n) for n in BASELINE_NAMES}
    for name, data in blobs.items():
        if digest(data) != provenance["members"][name]["sha256"] or len(data) != provenance["members"][name]["bytes"]:
            raise ValueError("Baseline member hash mismatch")
    if blobs["summary.json"] != (ROOT / "docs/legacy/audit-summary-v011.json").read_bytes() or digest(blobs["summary.json"]) != SUMMARY_SHA:
        raise ValueError("Frozen summary changed")
    summary, coverage = json.loads(blobs["summary.json"]), json.loads(blobs["coverage.json"])
    if [json.loads(x) for x in blobs["function_status.jsonl"].splitlines()] != coverage["functions"] or summary["counts"] != coverage["counts"]:
        raise ValueError("Baseline records inconsistent")
    claims = {c['id']: c for c in coverage['claims']}
    attached = set()
    for f in coverage['functions']:
        for i in f['claims']:
            c = claims.get(i)
            if c is None or c['domain'] != f['domain'] or address(c['address']) != address(f['address']):
                raise ValueError('Historical claim does not point to its recorded inventory function')
            attached.add(i)
    if attached != set(claims):
        raise ValueError('Historical claims contain unmapped records')
    return summary, coverage, provenance


def body_assembly(row):
    """Strict metadata validation; missing/preview/cancelled bodies stay raw-only."""
    if not isinstance(row, dict):
        return False, [], "not an object"
    body = row.get("disassembly", row)
    if not isinstance(body, dict):
        return False, [], "missing body object"
    if row.get('truncated') is True or row.get('complete') is False:
        return False, [], 'outer record explicitly incomplete'
    if body.get("truncated") is True or body.get("complete") is False:
        return False, [], "body explicitly incomplete"
    asm = body.get("asm")
    if not isinstance(asm, dict) or address(asm.get("start_ea")) is None:
        return False, [], "no valid ASM start"
    start = address(asm["start_ea"])
    if address(body.get("addr")) != start or address(row.get("addr")) != start:
        return False, [], "body address differs from ASM start"
    count, total = body.get("instruction_count"), body.get("total_instructions")
    cursor = body.get("cursor")
    if not nonnegative_int(count) or not nonnegative_int(total) or count <= 0 or count != total:
        return False, [], "invalid aggregate counts"
    if not isinstance(cursor, dict) or cursor.get("done") is not True or cursor.get("cancelled", False) is not False or cursor.get("next") is not None:
        return False, [], "aggregate cursor not explicitly finished"
    if body is not row:
        for key,expected in [('instruction_count',count),('total_instructions',total),('offset',0)]:
            if key in row and (not nonnegative_int(row[key]) or row[key]!=expected):
                return False, [], 'outer metadata contradicts disassembly'
        if 'cursor' in row:
            outer=row['cursor']
            if not isinstance(outer,dict) or outer.get('done') is not True or outer.get('cancelled',False) is not False or outer.get('next') is not None:
                return False, [], 'outer cursor does not confirm completion'
    lines = asm.get("lines")
    def valid_lines(items):
        return isinstance(items, list) and bool(items) and all(isinstance(x, dict) and address(x.get("addr")) is not None and isinstance(x.get("instruction"), str) and bool(x["instruction"].strip()) for x in items)
    if not valid_lines(lines) or len(lines) != count:
        return False, [], "invalid lines or count"
    addrs = [address(x["addr"]) for x in lines]
    if addrs[0] != start or len(set(addrs)) != len(addrs) or any(b <= a for a, b in zip(addrs, addrs[1:])):
        return False, [], "line addresses do not form a unique ordered body"
    if "offset" in body and (not nonnegative_int(body["offset"]) or body["offset"] != 0):
        return False, [], "aggregate offset is not zero"
    if "pages" in row:
        pages = row["pages"]
        if not isinstance(pages, list) or not pages:
            return False, [], "invalid pages"
        gathered, index = [], 0
        for i, page in enumerate(pages):
            if not isinstance(page, dict) or page.get("complete") is False or page.get("truncated") is True:
                return False, [], "invalid/incomplete page"
            pa, pc = page.get("asm"), page.get("cursor")
            if not isinstance(pa, dict) or address(pa.get("start_ea")) != start or not valid_lines(pa.get("lines")):
                return False, [], "invalid page ASM"
            n = page.get("instruction_count")
            if not nonnegative_int(n) or n != len(pa["lines"]) or not nonnegative_int(page.get("total_instructions")) or page["total_instructions"] != total:
                return False, [], "page counts disagree"
            if "offset" in page and (not nonnegative_int(page["offset"]) or page["offset"] != index):
                return False, [], "page offset disagrees"
            if not isinstance(pc, dict) or pc.get("cancelled", False) is not False:
                return False, [], "invalid/cancelled page cursor"
            index += n
            if i == len(pages) - 1:
                if pc.get("done") is not True or pc.get("next") is not None:
                    return False, [], "last page unfinished"
            elif pc.get("done", False) is not False or not nonnegative_int(pc.get("next")) or pc["next"] != index:
                return False, [], "page cursor skips/repeats instructions"
            gathered.extend(pa["lines"])
        if gathered != lines or index != total:
            return False, [], "page aggregate differs from recorded body"
    return True, addrs, "complete recorded ASM metadata"


def original_spans(row):
    spans = []
    raw = row.get("originalBytes", row.get("original_bytes", []))
    if isinstance(raw, str):
        raw = [{"addr": row.get("addr"), "data": raw}]
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    for item in raw:
        if not isinstance(item, dict) or address(item.get("addr")) is None or not isinstance(item.get("data"), str):
            return []
        tokens = item["data"].split()
        if not tokens or any(not re.fullmatch(r"(?:0x)?[0-9a-fA-F]{1,2}", x) for x in tokens):
            return []
        spans.append((address(item["addr"]), bytes(int(x, 16) for x in tokens)))
    return spans


def pe_comparer(binary):
    if not binary or not binary.is_file():
        return None
    data = binary.read_bytes()
    if digest(data) != TARGET_SHA:
        raise ValueError("Original PE has the wrong SHA256")
    off = struct.unpack_from("<I", data, 0x3C)[0]
    if data[off:off+4] != b"PE\0\0":
        raise ValueError("Not a PE")
    count = struct.unpack_from("<H", data, off+6)[0]
    optlen = struct.unpack_from("<H", data, off+20)[0]
    sections = []
    for i in range(count):
        s = off+24+optlen+40*i
        vsize, rva, rawlen, raw = struct.unpack_from("<IIII", data, s+8)
        sections.append((BASE+rva, rawlen, raw))
    def compare(addr, blob):
        for begin, size, raw in sections:
            delta = addr-begin
            if delta >= 0 and delta+len(blob) <= size:
                return data[raw+delta:raw+delta+len(blob)] == blob
        return False
    return compare


def evidence_inputs():
    paths = sorted(p for p in (ROOT / "docs/research").rglob("*.json") if OUT not in p.parents and p.name != "progress.json")
    provenance = read_json(OUT / "resource-import-provenance.json")
    for name, expected in provenance["members"].items():
        path = ROOT / provenance["snapshotDirectory"] / name
        data = path.read_bytes()
        if digest(data) != expected["sha256"] or len(data) != expected["bytes"]:
            raise ValueError("Resource evidence snapshot changed without explicit import")
        paths.append(path)
    return sorted(paths)


def resolve_reference(source, reference):
    if not isinstance(reference, str):
        return {"reference": reference, "status": "invalid"}
    name, _, fragment = reference.partition('#')
    for path in (ROOT / name, source.parent / name):
        try:
            rel = relative(path)
        except ValueError:
            continue
        if path.is_file():
            result={"reference": reference, "path": rel, "status": "exists", "sha256": digest(path.read_bytes())}
            if fragment:
                selector=re.fullmatch(r'(functions|code_ranges)\[(rva|addr|address)=((?:0x)?[0-9A-Fa-f]+)\]',fragment)
                if not selector:
                    result['status']='unsupported_fragment';return result
                data=read_json(path); collection,key,value=selector.groups()
                entries=data.get(collection,[]) if isinstance(data,dict) else []
                matches=[r for r in entries if isinstance(r,dict) and address(r.get(key))==address(value)] if isinstance(entries,list) else []
                if len(matches)!=1:
                    result['status']='missing_or_ambiguous_fragment';return result
                registry=module_domains(data)
                selected_domain=evidence_domain(matches[0],registry,document_domain(data,registry))
                if selected_domain not in (None,'native'):
                    result.update(status='excluded_domain',domain=selected_domain);return result
                result['selectedAddress']=hx(va(matches[0].get('addr',matches[0].get('address',matches[0].get('rva')))))
            return result
    return {"reference": reference, "status": "missing"}


def normalized_finding(value):
    return " ".join(value.split()).casefold()


def module_domains(doc):
    """Optional source-module registry. Never use a foreign module's RVA as retail."""
    registry = {}
    entries = doc.get('modules') if isinstance(doc, dict) else None
    # A keyed modules object is also used by verification summaries, not a registry.
    if entries is None or isinstance(entries, dict): return registry
    if not isinstance(entries, list): raise ValueError('Invalid modules registry')
    for item in entries:
        if not isinstance(item, dict) or not isinstance(item.get('id'), str) or not item['id'].strip():
            raise ValueError('Invalid module registry entry')
        key = item['id'].strip().casefold()
        if key in registry: raise ValueError('Duplicate module registry ID')
        base, sha = item.get('imageBase'), item.get('originalSha256')
        if address(base) is None or not isinstance(sha, str) or not re.fullmatch('[0-9a-fA-F]{64}', sha):
            raise ValueError('Module registry needs valid imageBase and originalSha256')
        target = address(base) == BASE and sha.casefold() == TARGET_SHA
        if key in ('retail', 'native') and not target:
            raise ValueError('Retail module registry differs from the exact target PE')
        registry[key] = {'domain': 'native' if target else key, 'imageBase': address(base), 'originalSha256': sha.casefold()}
    return registry


def evidence_domain(node, registry, inherited=None):
    """Resolve explicit scopes; legacy unlabelled evidence defaults to native.

    None is the legacy default, 'ambiguous' is a mixed document, and explicit
    native/foreign parent scopes cannot be contradicted by their descendants.
    """
    if not isinstance(node, dict): return inherited
    declarations = []
    for key in ('Domain', 'domain'):
        if key in node:
            value = node[key]
            if not isinstance(value, str) or not value.strip(): raise ValueError('Invalid evidence domain')
            value = value.strip().casefold()
            declarations.append('native' if value in ('native', 'retail') else value)
    module = None
    for key in ('module', 'Module'):
        if key not in node: continue
        value = node[key]
        if not isinstance(value, str) or not value.strip(): raise ValueError('Invalid evidence module')
        value = value.strip().casefold()
        info = registry.get(value)
        if info is not None:
            current = info['domain']; module = info
        elif value in ('retail', 'native', 'kh2_native.exe', 'kingdom hearts ii final mix.exe'):
            if registry: raise ValueError('Retail module ID is missing from declared registry')
            current = 'native'
        else:
            current = value if not registry else 'unregistered:' + value
        declarations.append(current)
    bases = [address(node[k]) for k in ('imageBase', 'imagebase') if k in node]
    hashes = [node[k] for k in ('originalSha256', 'targetSha256') if k in node]
    if any(x is None for x in bases) or len(set(bases)) > 1:
        raise ValueError('Invalid or conflicting evidence image base')
    if any(not isinstance(x, str) or not re.fullmatch('[0-9a-fA-F]{64}', x) for x in hashes):
        raise ValueError('Invalid evidence original SHA256')
    hashes = [x.casefold() for x in hashes]
    if len(set(hashes)) > 1: raise ValueError('Conflicting evidence original SHA256')
    if module and (bases and bases[0] != module['imageBase'] or hashes and hashes[0] != module['originalSha256']):
        raise ValueError('Evidence row contradicts its module registry')
    if len(set(declarations)) > 1: raise ValueError('Evidence domain/module conflict')
    local = declarations[0] if declarations else None
    domain_modules = [m for m in registry.values() if m['domain'] == local]
    if len(domain_modules) == 1:
        declared = domain_modules[0]
        if bases and bases[0] != declared['imageBase'] or hashes and hashes[0] != declared['originalSha256']:
            raise ValueError('Evidence fingerprint contradicts its declared domain')
    if local is None and (bases or hashes):
        candidates = {m['domain'] for m in registry.values() if
                      (not bases or bases[0] == m['imageBase']) and (not hashes or hashes[0] == m['originalSha256'])}
        is_target = (not bases or bases[0] == BASE) and (not hashes or hashes[0] == TARGET_SHA)
        local = 'native' if is_target else next(iter(candidates)) if len(candidates) == 1 else 'external_unidentified'
    if local == 'native' and (bases and bases[0] != BASE or hashes and hashes[0] != TARGET_SHA):
        raise ValueError('Native evidence metadata differs from the exact target PE')
    if inherited not in (None, 'ambiguous') and local is not None and local != inherited:
        raise ValueError('Evidence scope contradicts its parent domain')
    return local if local is not None else inherited


def document_domain(doc, registry):
    scope = evidence_domain(doc, registry)
    if scope is not None: return scope
    domains = {m['domain'] for m in registry.values()}
    return next(iter(domains)) if len(domains) == 1 else 'ambiguous' if domains else None


def retail_record(row, registry, scope):
    return evidence_domain(row, registry, scope) in (None, 'native')


def normalize_body(row):
    # Documented alternate export shape: {addr,info,asm:{addr,asm,...},bytes:{result:[]}}.
    # Do not infer missing counts, completion or bytes.
    if isinstance(row,dict) and isinstance(row.get('asm'),dict) and isinstance(row['asm'].get('asm'),dict):
        info=row.get('info'); raw=row.get('bytes')
        result={key:row[key] for key in ('addr','complete','truncated','cursor','instruction_count','total_instructions','offset','pages') if key in row}
        result.update({'size':info.get('size') if isinstance(info,dict) else None,
                       'disassembly':row['asm'], 'original_bytes':raw.get('result',[]) if isinstance(raw,dict) else []})
        return result
    if isinstance(row,dict) and isinstance(row.get('analysis'),dict) and isinstance(row.get('bytes'),str):
        normalized=dict(row); normalized['originalBytes']=row['bytes'];return normalized
    return row


def classify_address(a, inventory, ranges, owners):
    if a in inventory:
        return a, "exact_inventory_function_start"
    if a in ranges:
        return None, "separate_code_range_not_inventory_function"
    if len(owners.get(a, set())) == 1:
        return next(iter(owners[a])), "instruction_inside_evidenced_function"
    if len(owners.get(a, set())) > 1:
        return None, "ambiguous_instruction_owner"
    return None, "unresolved_or_nonfunction_address"


def has_raw_code(row, start, size):
    """A metadata shell or original bytes alone is not a code-content witness."""
    if not isinstance(row,dict): return False
    analysis=row.get('analysis')
    if isinstance(analysis,dict) and not analysis.get('decompile_error') and isinstance(analysis.get('decompile'),str) and analysis['decompile'].strip():
        return True
    pseudocode=row.get('pseudocode')
    if isinstance(pseudocode,dict) and isinstance(pseudocode.get('code'),str) and pseudocode['code'].strip():
        return True
    body=row.get('disassembly',row)
    asm=body.get('asm') if isinstance(body,dict) else None
    lines=asm.get('lines') if isinstance(asm,dict) else None
    if isinstance(lines,list) and start is not None and type(size) is int and size>0:
        for line in lines:
            if isinstance(line,dict):
                a=address(line.get('addr'));text=line.get('instruction')
                if a is not None and start<=a<start+size and isinstance(text,str) and text.strip(): return True
    return False


def run(binary):
    summary, baseline, provenance = load_baseline()
    source_names = archive_inventory(ROOT / "docs/legacy/KH2_Trainer_v0.11_Source.zip", SOURCE_SHA)
    native = {address(x["address"]): x for x in baseline["functions"] if x["domain"] == "native"}
    if len(native) != summary["counts"]["native"]["total"] or sum(bool(x["claims"]) for x in native.values()) != summary["counts"]["native"]["specific_static_claim"]:
        raise ValueError("Baseline address inventory/claim totals do not reconcile")
    compare = pe_comparer(binary)
    inputs, current_claims, evidence, excluded = [], [], [], []
    body_owners = defaultdict(set)
    raw_files = defaultdict(list)
    docs = []
    for path in evidence_inputs():
        data = path.read_bytes(); doc = json.loads(data)
        name = relative(path)
        inputs.append({"path": name, "bytes": len(data), "sha256": digest(data)})
        docs.append((path, doc))
        if not isinstance(doc, (dict,list)):
            continue
        registry=module_domains(doc); scope=document_domain(doc,registry)
        def admitted(row,pointer,kind,parent=scope):
            domain=evidence_domain(row,registry,parent)
            if domain in (None,'native'): return True
            excluded.append({'source':name,'pointer':pointer,'kind':kind,'domain':domain,
                             'module':row.get('module',row.get('Module')) if isinstance(row,dict) else None,
                             'addressAsRecorded':row.get('addr',row.get('Address')) if isinstance(row,dict) else None,
                             'reason':'mixed_module_row_needs_explicit_domain' if domain=='ambiguous' else 'outside_retail_native_domain',
                             'countedAsRetailEvidence':False,'originalRetailPeComparisonAttempted':False})
            return False
        funcs = doc.get("functions", []) if isinstance(doc,dict) else doc
        if isinstance(funcs, list):
            for i, row in enumerate(funcs):
                pointer = f"$.functions[{i}]" if isinstance(doc,dict) else f"$[{i}]"
                if not isinstance(row,dict) or not admitted(row,pointer,'function'): continue
                row = normalize_body(row)
                if not isinstance(row, dict) or not ("asm" in row or "disassembly" in row or isinstance(row.get('analysis'),dict) and isinstance(row['analysis'].get('decompile'),str)):
                    continue
                a = va(row.get("addr")); complete, lines, reason = body_assembly(row)
                analysis=row.get('analysis')
                size = row.get("size", analysis.get("size") if isinstance(analysis,dict) else None)
                size = address(size) if isinstance(size, str) else size
                spans = original_spans(row)
                byte_count = sum(len(b) for _, b in spans)
                contiguous = bool(spans) and spans[0][0] == a and all(x+len(b) == y for (x,b),(y,_) in zip(spans,spans[1:])) and type(size) is int and byte_count == size
                known = a in native
                extent_ok = known and size == native[a]["size"] and bool(lines) and all(a <= x < a+size for x in lines)
                verified = all(compare(x,b) for x,b in spans) if compare and spans else None
                full = complete and extent_ok and contiguous
                raw_content=has_raw_code(row,a,size)
                pointer = f"$.functions[{i}]" if isinstance(doc,dict) else f"$[{i}]"
                preview=analysis.get('disasm') if isinstance(analysis,dict) else None
                declared_count=preview.get('instruction_count') if isinstance(preview,dict) else None
                item = {"id": len(evidence), "source": name, "pointer": pointer, "address": hx(a), "knownFunctionStart": known, "hasRawCode":raw_content, "completeRecordedAsm": full, "metadataReason": reason, "extentAndInventoryMatch": extent_ok, "recordedSize": size, "instructionCount": len(lines), "declaredBatchAsmInstructionCount":declared_count if nonnegative_int(declared_count) else None, "recordedByteCount": byte_count, "contiguousBodyBytes": contiguous, "byteExtentMatchesInventory":known and size==native[a]['size'] and contiguous, "originalPeBytesMatch": verified, "status": "complete_recorded_body" if full else "raw_or_incomplete_body" if raw_content else "metadata_without_code_content"}
                evidence.append(item); raw_files[name].append(item)
                if full:
                    for line in lines:
                        body_owners[line].add(a)
        ranges = doc.get("code_ranges", []) if isinstance(doc,dict) else []
        if isinstance(ranges, list):
            for i, row in enumerate(ranges):
                if not isinstance(row, dict): continue
                if not admitted(row,f'$.code_ranges[{i}]','code_range'): continue
                a = va(row.get("addr")); spans = original_spans(row)
                end = address(row.get("end_exclusive"))
                asm = row.get('asm')
                lines = asm.get('lines',[]) if isinstance(asm,dict) else []
                line_addresses = [address(x.get("addr")) if isinstance(x,dict) else None for x in lines] if isinstance(lines,list) else []
                valid_range = (a is not None and end is not None and end > a and len(spans)==1 and spans[0][0]==a and len(spans[0][1])==end-a and type(row.get("observed_line_count")) is int and row["observed_line_count"]==len(line_addresses) and bool(line_addresses) and line_addresses[0]==a and all(x is not None and a<=x<end for x in line_addresses) and len(set(line_addresses))==len(line_addresses))
                item = {"id": len(evidence), "source": name, "pointer": f"$.code_ranges[{i}]", "address": hx(a), "knownFunctionStart": a in native, "completeRecordedAsm": False, "recordedRangeValidated":valid_range, "observedInstructionCount":len(line_addresses), "recordedByteCount": sum(len(b) for _,b in spans), "originalPeBytesMatch": all(compare(x,b) for x,b in spans) if compare and spans else None, "status": "code_range_not_inventory_function", "note": row.get("note")}
                evidence.append(item); raw_files[name].append(item)
        # Raw analyze_batch entries are deliberately raw, never promoted by truncated:false.
        def walk(value, pointer, parent=scope):
            if isinstance(value, dict):
                local=evidence_domain(value,registry,parent)
                analysis = value.get("analysis")
                candidate=isinstance(analysis, dict) and isinstance(analysis.get("decompile"), str) and analysis['decompile'].strip() and not analysis.get('decompile_error')
                if candidate and admitted(value,pointer,'nested_preview',parent) and va(value.get("addr")) in native:
                    item = {"id": len(evidence), "source": name, "pointer": pointer, "address": hx(va(value["addr"])), "knownFunctionStart": True, "hasRawCode":True, "completeRecordedAsm": False, "status": "pseudocode_or_preview_only"}
                    evidence.append(item);raw_files[name].append(item)
                if local not in (None,'native','ambiguous'):
                    if not candidate: admitted(value,pointer,'foreign_subtree',parent)
                    return
                for k,v in value.items():
                    if k not in ("functions", "code_ranges", "modules"): walk(v, pointer+"."+k,local)
            elif isinstance(value, list):
                for i,v in enumerate(value): walk(v, pointer+f"[{i}]",parent)
        walk(doc, "$")
    range_addresses = {address(e["address"]) for e in evidence if e["status"] == "code_range_not_inventory_function"}
    for path, doc in docs:
        if not isinstance(doc, dict): continue
        registry=module_domains(doc); scope=document_domain(doc,registry)
        for collection in ("claims", "Claims", "findings"):
            rows = doc.get(collection, [])
            if not isinstance(rows, list): continue
            for i, row in enumerate(rows):
                if not isinstance(row, dict) or not isinstance(row.get("Finding"), str) or not row["Finding"].strip() or address(row.get("addr",row.get('Address'))) is None:
                    continue
                domain=evidence_domain(row,registry,scope)
                if domain not in (None,'native'):
                    excluded.append({'source':relative(path),'pointer':f'$.{collection}[{i}]','kind':'claim','domain':domain,
                                     'module':row.get('module',row.get('Module')),'addressAsRecorded':row.get('addr',row.get('Address')),
                                     'reason':'mixed_module_row_needs_explicit_domain' if domain=='ambiguous' else 'outside_retail_native_domain',
                                     'countedAsRetailEvidence':False,'originalRetailPeComparisonAttempted':False})
                    continue
                a = va(row.get("addr",row.get('Address')))
                owner, classification = classify_address(a,native,range_addresses,body_owners)
                refs = [resolve_reference(path,r) for r in row.get("Evidence",[]) ] if isinstance(row.get("Evidence"), list) else []
                selected_evidence={e['id']:e for r in refs if r['status']=='exists' for e in raw_files.get(r['path'],[]) if 'selectedAddress' not in r or e['address']==r['selectedAddress']}
                owner_evidence = [e for e in selected_evidence.values() if address(e["address"]) == owner and owner is not None]
                has_code = any(e.get('hasRawCode') for e in owner_evidence)
                complete = any(e.get("completeRecordedAsm") for e in owner_evidence)
                supported = owner is not None and bool(refs) and all(r["status"]=="exists" for r in refs) and has_code
                range_evidence = [e for e in selected_evidence.values() if address(e["address"])==a and e.get("recordedRangeValidated")]
                range_supported = owner is None and bool(refs) and all(r["status"]=="exists" for r in refs) and bool(range_evidence)
                current_claims.append({"id": f"new:{len(current_claims)}", "domain": "native", "citedAddress": hx(a), "functionAddress": hx(owner), "classification": classification, "finding": row["Finding"], "limitations": row.get("Limitations"), "source": relative(path), "pointer": f"$.{collection}[{i}]", "references": refs, "evidenceIds": [e["id"] for e in owner_evidence+range_evidence], "supportedRecordedClaim": supported, "supportedCodeRangeClaim": range_supported, "completeRecordedAsm": complete, "status": "specific_static_claim_with_full_asm" if supported and complete else "specific_static_claim_with_raw_code" if supported else "specific_static_code_range_claim_not_function" if range_supported else "unresolved_claim", "fullSemanticReview": "not_established"})
    # Duplicate claims remain visible as occurrences; only unique function addresses change totals.
    legacy_claims = []
    for c in baseline["claims"]:
        legacy_claims.append({"id": "legacy:"+str(c["id"]), "domain": c["domain"], "functionAddress": c.get("address"), "citedAddress": c.get("cited_address"), "source": c.get("source"), "pointer": c.get("json_pointer"), "finding": c.get("finding"), "sourceInFrozenSourceArchive": c.get("source") in source_names, "status": "legacy_recorded_claim_not_revalidated", "fullSemanticReview": "not_established"})
    groups = defaultdict(list)
    for c in legacy_claims+current_claims:
        key = (c["domain"], c.get("functionAddress") or c.get("citedAddress"), normalized_finding(c.get("finding") or ""))
        groups[key].append(c["id"])
    duplicate_groups = [ids for ids in groups.values() if len(ids)>1]
    new_by_fn = defaultdict(list)
    for c in current_claims:
        if c["supportedRecordedClaim"]: new_by_fn[address(c["functionAddress"])].append(c)
    raw_by_fn = defaultdict(list)
    for e in evidence:
        if e["knownFunctionStart"]: raw_by_fn[address(e["address"])].append(e)
    legacy_full = {address(e["address"]) for e in baseline["targeted_raw_evidence"] if e.get("assembly") is True and e.get("complete") is True}
    new_full = {address(e["address"]) for e in evidence if e.get("completeRecordedAsm")}
    added = sorted(a for a in new_by_fn if not native[a]["claims"])
    repeated = sorted(a for a in new_by_fn if native[a]["claims"])
    functions = []
    for f in baseline["functions"]:
        a = address(f["address"]); is_native = f["domain"] == "native"
        new = new_by_fn.get(a,[]) if is_native else []
        claimed = bool(f["claims"] or new)
        functions.append({"domain": f["domain"], "address": f["address"], "name": f["name"], "size": f["size"], "inventoryStatus": "frozen_v011_inventory", "legacyExport": f.get("export"), "legacyEvidenceTier": f.get("evidence_tier"), "legacyClaimIds": ["legacy:"+str(x) for x in f["claims"]], "newClaimIds": [c["id"] for c in new], "newEvidenceIds": [e["id"] for e in raw_by_fn.get(a,[])] if is_native else [], "completeAsm": {"legacyRecorded": a in legacy_full if is_native else f.get("evidence_tier")==3, "newlyValidatedMetadata": a in new_full if is_native else False}, "claimStatus": "specific_recorded_claim" if claimed else "no_specific_recorded_claim", "change": "new_specific_claim_on_existing_function" if a in added and is_native else "additional_claim_on_already_documented_function" if new else "unchanged", "fullSemanticReview": "not_established"})
    # A foreign claim container can also be visited by the preview walker. Keep
    # one source/pointer/domain receipt, with the later explicit claim classification.
    excluded=list({(e['source'],e['pointer'],e['domain']):e for e in excluded}.values())
    count = len(native); baseline_count = sum(bool(x["claims"]) for x in native.values())
    out_summary = {
        "schema": 1, "targetSha256": TARGET_SHA, "imageBase": hx(BASE),
        "method": {"baseline": "Hash-pinned historical full audit; original counts/tiers are preserved as historical recorded evidence, not rerun proof.", "currentClaims": "Only explicit top-level claims/Claims/findings with addr/Address, Finding and resolvable evidence are considered. References, names, callsites, raw exports and test counts alone do not create semantic claims.", "deduplication": "Counts use canonical native function-start addresses. Interior instructions map only through a validated full-body instruction list. Separate callback ranges, unresolved addresses and duplicate occurrences do not expand the function inventory.", "semanticLimit": "One concrete finding does not prove all branches, side effects, resource lifetimes or live behavior. No function is promoted to complete semantic understanding.", "domains": "Native, CIL and shader addresses stay separate. Six bodyless CIL metadata placeholders remain separate from 439 real CIL bodies.", "asmLimit": "Complete current ASM requires finished aggregate/page cursors, matching counts, unique ordered instruction addresses, exact existing inventory extent and contiguous original body bytes. analyze_batch previews are raw-only. Original byte comparison is independently reported."},
        "baselineCounts": summary["counts"],
        "native": {"inventoryFunctions": count, "newInventoryFunctions": 0, "historicalValidExports": summary["counts"]["native"]["valid_exports"], "legacyFunctionsWithSpecificClaim": baseline_count, "newUniqueFunctionsWithSpecificClaim": len(added), "alreadyClaimedFunctionsWithAdditionalFindings": len(repeated), "mergedFunctionsWithSpecificClaim": baseline_count+len(added), "functionsWithoutSpecificClaim": count-baseline_count-len(added), "legacyRecordedFullAsmFunctions": len(legacy_full & set(native)), "currentFullAsmFunctions": len(new_full), "additionalFullAsmFunctionsBeyondLegacy": len(new_full-legacy_full), "mergedRecordedFullAsmFunctions": len((legacy_full|new_full)&set(native)), "completeSemanticFunctionCount": None, "completeSemanticFunctionCountReason": "Not measured or established by these inputs."},
        "newClaims": {"occurrences": len(current_claims), "supportedFunctionClaimOccurrences": sum(c["supportedRecordedClaim"] for c in current_claims), "supportedCodeRangeClaimOccurrences":sum(c["supportedCodeRangeClaim"] for c in current_claims), "canonicalFunctions": len(new_by_fn), "classifications": dict(Counter(c["classification"] for c in current_claims)), "unresolvedOccurrences": sum(not(c["supportedRecordedClaim"] or c["supportedCodeRangeClaim"]) for c in current_claims), "duplicateClaimGroupsAcrossAllRecordedSources": len(duplicate_groups)},
        "currentEvidence": {"records": len(evidence), "completeBodyRecords": sum(e.get("completeRecordedAsm",False) for e in evidence), "originalPeCompared": compare is not None, "recordedByteComparisonsPassing": sum(e.get("originalPeBytesMatch") is True for e in evidence), "recordedByteComparisonsFailing": sum(e.get("originalPeBytesMatch") is False for e in evidence), "note": "Body occurrences from overlapping investigations are not unique functions."},
        "excludedDomains": {"occurrences":len(excluded),"byDomain":dict(Counter(e['domain'] for e in excluded)),
                            "byKind":dict(Counter(e['kind'] for e in excluded)),"records":excluded,
                            "scope":"These records are outside the retail-native evidence/claim totals; no original-retail byte comparison was attempted. Ambiguous mixed-module rows are not guessed. Contradictory metadata and actual retail byte mismatches remain fatal."},
        "newUniqueFunctionAddresses": [hx(a) for a in added], "revisitedFunctionAddresses": [hx(a) for a in repeated],
        "sourceArchive": {"path": "docs/legacy/KH2_Trainer_v0.11_Source.zip", "sha256": SOURCE_SHA, "members":len(source_names), "containsFullAudit": False},
        "legacyClaimSources": {"claimOccurrences":len(legacy_claims),"sourcePathPresentInFrozenSourceArchive":sum(c['sourceInFrozenSourceArchive'] for c in legacy_claims),"sourcePathAbsentFromFrozenSourceArchive":sum(not c['sourceInFrozenSourceArchive'] for c in legacy_claims),"scope":"All historical claim text/source pointers are preserved in the baseline full audit; absence here is not silently treated as a fresh source verification."},
        "baselineArchive": {"path":provenance["archive"],"sha256":provenance["sha256"]}, "inputs":inputs,
        "validationScope": "Static reconciliation, strict metadata checks and optional original PE byte comparison. No IDB/game/save/UI/network writes, builds or gameplay tests."
    }
    if out_summary["currentEvidence"]["recordedByteComparisonsFailing"]:
        raise ValueError("Recorded current evidence differs from exact original PE")
    for entry in inputs:
        if digest((ROOT/entry['path']).read_bytes()) != entry['sha256']:
            raise ValueError("Research inputs changed during coverage generation; rerun from a stable state")
    write_jsonl(OUT / "function_status.jsonl", functions)
    write_jsonl(OUT / "claims.jsonl", legacy_claims+current_claims)
    write_jsonl(OUT / "evidence.jsonl", evidence)
    write_json(OUT / "duplicates.json", {"definition":"same domain, canonical address and whitespace/case-normalized finding text; retained occurrences, counted functions once", "groups":duplicate_groups})
    write_json(OUT / "summary.json", out_summary)
    lines = ["# Analysis coverage reconciliation", "", f"Native inventory: **{count:,}** functions. The frozen v0.11 audit recorded specific claims for **{baseline_count:,}**.", f"New work adds specific claims to **{len(added)}** previously undocumented function addresses and revisits **{len(repeated)}** already documented functions.", f"Merged: **{baseline_count+len(added):,}** functions with at least one recorded specific claim; **{count-baseline_count-len(added):,}** without one.", "", "These are claim counts, not fully understood functions. Complete semantic review is **not established**. Historical export counts and ASM evidence remain separate.", "", "## Provenance", "", "The old Source.zip did not include its full coverage audit. The matching old summary was byte-identical to the frozen v0.11 summary; its full records were imported into baseline-v011-full-audit.zip with member hashes. Regeneration does not need the old workspace.", "", "## New function addresses", "", "| Function | Specific finding | Source |", "|---|---|---|"]
    for a in added:
        c=new_by_fn[a][0]
        lines.append(f"| {hx(a)} | {c['finding'].replace('|','/')} | {c['source']} {c['pointer']} |")
    lines += ["", "## Code ranges and unresolved claims", "", "| Address | Classification | Finding |", "|---|---|---|"]
    for c in current_claims:
        if not c["supportedRecordedClaim"]:
            lines.append(f"| {c['citedAddress']} | {c['classification']} | {c['finding'].replace('|','/')} |")
    lines += ["", "## Limits", "", "- Raw exports, callees, vtable slots and test results do not count as semantic claims.", "- New interior-address claims need an instruction-to-function match. A separately exported callback range is not silently promoted to an IDA function.", "- Legacy claims retain their original source pointers and historical status; this script does not independently re-review all of them.", "- Current complete ASM metadata is checked conservatively. Original bytes are compared only when the exact PE is available, and this is reported separately.", "- No all-branches or live-game correctness percentage is inferred. See summary.json, claims.jsonl and function_status.jsonl for address-level records."]
    (OUT/"report.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(json.dumps({"native":out_summary["native"],"newClaims":out_summary["newClaims"],"currentEvidence":out_summary["currentEvidence"]},indent=2))


def self_test():
    checks=0
    def check(condition, message):
        nonlocal checks
        checks+=1
        if not condition: raise AssertionError(message)
    body={"addr":"0x140001000","asm":{"start_ea":"0x140001000","lines":[{"addr":"140001000","instruction":"nop"},{"addr":"140001001","instruction":"ret"}]},"instruction_count":2,"total_instructions":2,"cursor":{"done":True}}
    check(body_assembly(body)[0],"complete body")
    for field,values in {"instruction_count":[None,"2",True,-1,0,1,3],"total_instructions":[None,"2",True,-1,0,1,3],"cursor":[None,{}, {"done":False},{"done":True,"next":1},{"done":True,"cancelled":True} ]}.items():
        for value in values:
            b=copy.deepcopy(body);b[field]=value;check(not body_assembly(b)[0],f"invalid {field} {value}")
    for value in (None,{},[],[{}],[{"addr":"bad_address","instruction":"ret"}],[{"addr":"140001000","instruction":"nop"},"garbage"],[{"addr":"140001000","instruction":"nop"}]*2):
        b=copy.deepcopy(body);b["asm"]["lines"]=value;check(not body_assembly(b)[0],"invalid lines")
    for value in (None,"bad_address","0x140002000"):
        b=copy.deepcopy(body);b["asm"]["start_ea"]=value;check(not body_assembly(b)[0],"invalid/mismatched start")
    pages=[]
    for i in range(2):
        p=copy.deepcopy(body);p['asm']['lines']=[body['asm']['lines'][i]];p['instruction_count']=1;p['offset']=i;p['cursor']={'next':1} if i==0 else {'done':True};pages.append(p)
    combined=copy.deepcopy(body);combined['pages']=pages
    check(body_assembly(combined)[0],"full pages")
    for field,value in [('offset',9),('complete',False),('instruction_count',None),('total_instructions',3),('cursor',{'cancelled':True}),('cursor',{'next':None}),('cursor',{'next':True})]:
        b=copy.deepcopy(combined);b['pages'][0][field]=value;check(not body_assembly(b)[0],f"bad page {field}")
    for field,value in [('cursor',{'cancelled':True}),('cursor',{'done':False,'next':2}),('instruction_count',1),('total_instructions',1),('offset',True)]:
        b=copy.deepcopy(combined);b[field]=value;check(not body_assembly(b)[0],"aggregate contradicts pages")
    check(not body_assembly({'addr':'0x140001000','assembly':'ret'})[0],"bare text never complete")
    for value in (True,None,{},'xyz','-1'): check(address(value) is None,"reject invalid address")
    check(va('3EF800')==0x1403EF800,"RVA normalization")
    check(va('0x1403EF800')==0x1403EF800,"VA normalization")
    for name in ('../x','/x','C:/x','x/../y','x\\y','x//y'): check(not canonical_member(name),"unsafe archive name")
    check(canonical_member('docs/research/file.json'),"safe archive name")
    check(normalized_finding(' A  B\nC ')==normalized_finding('a b c'),"claim text deduplication")
    inventory={0x140001000:{}}
    owners={0x140001001:{0x140001000},0x140003001:{0x140003000,0x140004000}}
    ranges={0x140002000}
    check(classify_address(0x140001000,inventory,ranges,owners)==(0x140001000,'exact_inventory_function_start'),'exact function')
    check(classify_address(0x140001001,inventory,ranges,owners)==(0x140001000,'instruction_inside_evidenced_function'),'instruction maps to one owner')
    check(classify_address(0x140002000,inventory,ranges,owners)==(None,'separate_code_range_not_inventory_function'),'callback does not create function')
    check(classify_address(0x140003001,inventory,ranges,owners)==(None,'ambiguous_instruction_owner'),'ambiguous owner does not create function')
    check(classify_address(0x142a00000,inventory,ranges,owners)==(None,'unresolved_or_nonfunction_address'),'data pointer does not create function')
    check(len({classify_address(a,inventory,ranges,owners)[0] for a in (0x140001000,0x140001001)})==1,'start plus instruction is one function')
    b=copy.deepcopy(body);b['addr']='0x140002000';check(not body_assembly(b)[0],'address mismatch rejected')
    check(original_spans({'original_bytes':{'addr':'140001000','data':'0x90 0xc3'}})==[(0x140001000,b'\x90\xc3')],'single code-range byte span')
    check(original_spans({'addr':'140001000','original_bytes':'0x90 0xc3'})==[(0x140001000,b'\x90\xc3')],'snake-case string bytes retain explicit address')
    check(original_spans({'original_bytes':'0x90 0xc3'})==[],'string bytes require a valid explicit address')
    check(original_spans({'addr':'140001000','original_bytes':'0x90 0x100'})==[],'string byte alias retains strict byte bounds')
    alternate={'addr':body['addr'],'info':{'size':2},'asm':body,'bytes':{'result':[{'addr':body['addr'],'data':'0x90 0xc3'}]}}
    check(body_assembly(normalize_body(alternate))[0],'nested tool-body shape retains valid explicit metadata')
    alternate['asm']=copy.deepcopy(body);alternate['asm'].pop('cursor')
    check(not body_assembly(normalize_body(alternate))[0],'normalization never supplies completion')
    alternate['info']=None;alternate['bytes']=None
    check(normalize_body(alternate)['size'] is None and original_spans(normalize_body(alternate))==[], 'null nested metadata remains unknown')
    batch={'addr':body['addr'],'analysis':{'size':'0x2','decompile':'void f() {}','disasm':{'lines':['140001000 nop','140001001 ret'],'instruction_count':2,'truncated':False}},'bytes':'0x90 0xc3'}
    normalized=normalize_body(batch)
    check(original_spans(normalized)==[(0x140001000,b'\x90\xc3')],'batch original bytes remain independently checkable')
    check(not body_assembly(normalized)[0],'batch preview metadata alone never upgraded to complete ASM')
    for key,value in [('complete',False),('truncated',True),('cursor',{'cancelled':True}),('cursor',{'done':False}),('cursor',{'done':True,'next':2}),('instruction_count',None),('total_instructions',1),('offset',True)]:
        wrapped={'addr':body['addr'],'disassembly':copy.deepcopy(body),key:value}
        check(not body_assembly(wrapped)[0],f'outer contradiction {key} rejected')
    check(not has_raw_code({'addr':body['addr'],'asm':{}},0x140001000,2),'empty ASM metadata is no raw code witness')
    check(not has_raw_code({'analysis':{'decompile':' '}},0x140001000,2),'blank pseudocode is no witness')
    check(not has_raw_code({'originalBytes':'0x90 0xc3'},0x140001000,2),'bytes alone never support semantic claim')
    check(has_raw_code(body,0x140001000,2),'addressed ASM is raw content')
    check(has_raw_code(batch,0x140001000,2),'nonblank actual pseudocode is raw content')
    retail={'id':'retail','imageBase':hx(BASE),'originalSha256':TARGET_SHA}
    panacea={'id':'panacea','imageBase':'0x180000000','originalSha256':'0'*64}
    mixed={'modules':[retail,panacea]}
    registry=module_domains(mixed); scope=document_domain(mixed,registry)
    check(scope=='ambiguous','mixed module header does not silently default to retail')
    check(retail_record(body,{},document_domain({},{})),'unlabelled legacy body keeps retail default')
    check(retail_record(dict(body,module='retail'),registry,scope),'mixed document explicit retail body admitted')
    check(not retail_record(dict(body,module='panacea'),registry,scope),'mixed foreign body excluded even at retail-looking VA')
    check(not retail_record(dict(body,addr='1000',module='panacea'),registry,scope),'foreign RVA never rebased to retail')
    check(not retail_record(body,registry,scope),'mixed unlabelled body is not guessed')
    for key in ('Domain','domain'):
        check(retail_record(dict(body,**{key:'native'}),registry,scope),'explicit native claim resolves mixed scope')
        check(not retail_record(dict(body,**{key:'panacea'}),registry,scope),'external claim excluded')
        check(not retail_record(dict(body,**{key:'cil'}),{},None),'CIL evidence never treated as retail native')
    for kind in ('functions','code_ranges','nested_preview','claims'):
        rows=[dict(body,module='retail'),dict(body,module='panacea'),copy.deepcopy(body)]
        calls=[]; accepted=[]
        # Same admission-before-normalization order as the production loops. The
        # comparer deliberately rejects foreign bytes; it must only see retail.
        for row in rows:
            if not retail_record(row,registry,scope): continue
            normalized=normalize_body(row); calls.append(normalized['addr']); accepted.append(normalized)
        check(len(accepted)==1 and len(calls)==1,f'{kind}: only retail reaches downstream normalization/comparison')
        check(accepted[0]['module']=='retail',f'{kind}: excluded rows cannot inflate totals')
    foreign_scope=document_domain({'module':'panacea','modules':[panacea]},module_domains({'modules':[panacea]}))
    check(not retail_record(body,module_domains({'modules':[panacea]}),foreign_scope),'unlabelled nested preview inherits foreign scope')
    check(not retail_record(dict(body,module='unlisted'),registry,scope),'unknown registry ID excluded instead of using legacy default')
    check(document_domain({'originalSha256':TARGET_SHA,'imageBase':hx(BASE)}, {})=='native','legacy explicit target fingerprint remains native')
    check(document_domain({'originalSha256':'1'*64,'imageBase':'0x180000000'}, {})=='external_unidentified','foreign header fingerprint cannot default to retail')
    def raises(call):
        try: call()
        except ValueError: return True
        return False
    invalid_nodes=[{'Domain':'native','module':'panacea'},{'Domain':'panacea','module':'retail'},
                   {'Domain':'native','domain':'cil'},{'module':'retail','imageBase':'0x180000000'},
                   {'module':'retail','originalSha256':'1'*64},{'module':'panacea','originalSha256':TARGET_SHA},
                   {'Domain':'panacea','originalSha256':TARGET_SHA},{'Domain':'panacea','imageBase':hx(BASE)},
                   {'Domain':'native','imageBase':'bad_address'},{'Domain':'native','imagebase':True},
                   {'Domain':'native','originalSha256':None},{'Domain':'native','targetSha256':'0'*64},
                   {'Domain':'native','originalSha256':TARGET_SHA,'targetSha256':'0'*64},
                   {'imageBase':hx(BASE),'imagebase':'0x180000000'}]
    for node in invalid_nodes:
        check(raises(lambda n=node:evidence_domain(n,registry,scope)),'contradictory/invalid domain metadata fails closed')
    for key in ('module','Module','Domain','domain'):
        for value in (None,True,0,[],{},''):
            check(raises(lambda k=key,v=value:evidence_domain({k:v},registry,scope)),f'malformed {key} rejected')
    check(raises(lambda:evidence_domain({'Domain':'native'},registry,'panacea')),'explicit foreign parent cannot be escaped by native child')
    check(raises(lambda:module_domains({'modules':[retail,retail]})),'duplicate module IDs rejected')
    for entries in (True,'retail',[None],[{}],[dict(retail,imageBase=None)],[dict(retail,originalSha256='1'*64)]):
        check(raises(lambda e=entries:module_domains({'modules':e})),'malformed or wrong retail registry rejected')
    check(module_domains({'modules':{'retail':{'functions':3}}})=={},'summary count dictionaries are not module registries')
    # Filtering never changes the byte comparator or turns a native mismatch
    # into success; the production run still raises for every False comparison.
    normalized=normalize_body(dict(batch,module='retail'))
    check(retail_record(normalized,registry,scope) and original_spans(normalized)==[(BASE+0x1000,b'\x90\xc3')],
          'admitted retail body preserves exact original bytes for mandatory comparison')
    # A fragment selecting external evidence must not be satisfied by another
    # retail row in the same file. No fixture files or archived code are opened.
    selected_doc={'modules':[retail,panacea],'functions':[
        {'rva':'1000','addr':'140001000','module':'retail'},
        {'rva':'2000','addr':'180002000','module':'panacea'},
        {'rva':'3000','addr':'140003000'}]}
    with patch.dict(globals(),{'read_json':lambda _:selected_doc}), patch.object(Path,'is_file',return_value=True), patch.object(Path,'read_bytes',return_value=b'fixture'):
        source=ROOT/'domain-test.json'
        external=resolve_reference(source,'domain-fixture.json#functions[rva=2000]')
        check(external['status']=='excluded_domain' and external['domain']=='panacea' and 'selectedAddress' not in external,
              'foreign fragment cannot supply retail claim evidence')
        selected=resolve_reference(source,'domain-fixture.json#functions[rva=1000]')
        check(selected['status']=='exists' and selected['selectedAddress']=='0x140001000','explicit retail fragment remains resolvable')
        ambiguous=resolve_reference(source,'domain-fixture.json#functions[rva=3000]')
        check(ambiguous['status']=='excluded_domain' and ambiguous['domain']=='ambiguous','unlabelled mixed fragment stays unresolved')
    OUT.mkdir(parents=True,exist_ok=True)
    write_json(OUT/'self-tests.json',{'script':relative(Path(__file__)),'scriptSha256':digest(Path(__file__).read_bytes()),'checks':checks,'failures':0,'scope':'Isolated metadata/address/path/domain regression checks; mixed-module functions/ranges/previews/claims excluded before retail normalization, inconsistent metadata rejected, legacy unlabelled inputs preserved. No game or archived code execution.'})
    print(f'{checks} checks, 0 failures')


def verify_reproducible(binary):
    outputs=('summary.json','function_status.jsonl','claims.jsonl','evidence.jsonl','duplicates.json','report.md')
    run(binary)
    first={name:digest((OUT/name).read_bytes()) for name in outputs}
    run(binary)
    second={name:digest((OUT/name).read_bytes()) for name in outputs}
    if first!=second:
        raise ValueError('Coverage outputs changed across identical-input regeneration')
    summary=read_json(OUT/'summary.json')
    functions=[json.loads(x) for x in (OUT/'function_status.jsonl').read_text(encoding='utf-8').splitlines()]
    claims=[json.loads(x) for x in (OUT/'claims.jsonl').read_text(encoding='utf-8').splitlines()]
    evidence=[json.loads(x) for x in (OUT/'evidence.jsonl').read_text(encoding='utf-8').splitlines()]
    identities={(x['domain'],x['address']) for x in functions}
    if len(identities)!=len(functions): raise ValueError('Duplicate function identity')
    native=[x for x in functions if x['domain']=='native']
    checked=summary['native']
    if len(native)!=checked['inventoryFunctions'] or sum(x['claimStatus']=='specific_recorded_claim' for x in native)!=checked['mergedFunctionsWithSpecificClaim']:
        raise ValueError('Per-function records do not match final totals')
    if checked['functionsWithoutSpecificClaim']+checked['mergedFunctionsWithSpecificClaim']!=len(native):
        raise ValueError('Claimed/open partition is inconsistent')
    ids={x['id'] for x in claims};eids={x['id'] for x in evidence}
    for f in functions:
        if not set(f['legacyClaimIds']+f['newClaimIds'])<=ids or not set(f['newEvidenceIds'])<=eids:
            raise ValueError('A per-function reference points to no record')
        if f['fullSemanticReview']!='not_established': raise ValueError('Unexpected complete-semantics promotion')
    for c in claims:
        if c['id'].startswith('new:'):
            if not set(c['evidenceIds'])<=eids: raise ValueError('Claim points to no evidence')
            if c['classification']=='separate_code_range_not_inventory_function' and c['functionAddress'] is not None:
                raise ValueError('A callback code range was incorrectly promoted')
    write_json(OUT/'reproducibility.json',{
        'status':'pass','script':relative(Path(__file__)),'scriptSha256':digest(Path(__file__).read_bytes()),
        'twoConsecutiveRunsByteIdentical':True,'outputSha256':second,
        'functionRecords':len(functions),'nativeFunctionRecords':len(native),'claimOccurrences':len(claims),'currentEvidenceRecords':len(evidence),
        'checks':['two consecutive generations byte-identical','unique domain/address identities','native totals reconcile','claimed/open partition reconciles','all claim/evidence IDs resolve','callback code ranges not promoted','no function marked fully semantically understood'],
        'selfTests':read_json(OUT/'self-tests.json'),
        'scope':'Own parser/reconciliation verification only; no product build or game execution.'})
    print('Reproducibility and output-reference verification: PASS')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--import-baseline',type=Path)
    parser.add_argument('--import-resources',type=Path)
    parser.add_argument('--binary',type=Path,default=DEFAULT_BINARY)
    parser.add_argument('--self-test',action='store_true')
    parser.add_argument('--verify-reproducible',action='store_true')
    args=parser.parse_args();OUT.mkdir(parents=True,exist_ok=True)
    if args.self_test:
        self_test();return
    if args.import_baseline: import_baseline(args.import_baseline)
    if args.import_resources: import_resources(args.import_resources)
    if args.verify_reproducible: verify_reproducible(args.binary)
    else: run(args.binary)


if __name__=='__main__':
    main()
