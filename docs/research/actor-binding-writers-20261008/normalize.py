"""Adapt frozen evidence to the existing coverage schema; no IDA or game calls.

Default writes only this folder's coverage-evidence.json, claims.json and
manifest.json. --check compares their deterministic contents without writing.
The central coverage module is imported only for read-only validation helpers.
"""
from pathlib import Path
import argparse
import copy
import hashlib
import importlib.util
import json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PINS = {
    "evidence.json": "ca89139dbb0f9806141260dd0761be8f4ffee92fad16c4ee2bb8aa39be5a3f1b",
    "report.json": "032082e676e4d043cf72bb2985c0e269f44c739a4fab2cba953dba8ee4806b03",
    "verify.py": "08202e08c096176f0faaa0749adf3793e6d666af290ba7c421301a3aa5ed6660",
    "verification.json": "50bb7f6428a480999758a96b619d69f28e64253b129449cbd2a0dfab8ddb7bfd",
}
LIMIT = ("Bounded static claim only. No complete writer/alias census, common "
         "thread exclusion, live-game validation or complete semantic review.")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_coverage():
    path = ROOT / "scripts/update-analysis-coverage.py"
    spec = importlib.util.spec_from_file_location("coverage_read_only", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, path


def derive():
    source_bytes = {name: (HERE / name).read_bytes() for name in PINS}
    for name, expected in PINS.items():
        require(sha(source_bytes[name]) == expected, "Frozen source changed: " + name)
    evidence = json.loads(source_bytes["evidence.json"])
    report = json.loads(source_bytes["report.json"])
    coverage, parser_path = load_coverage()
    require(evidence["original_sha256"] == report["original_sha256"] == coverage.TARGET_SHA,
            "Target fingerprint mismatch")
    require(int(evidence["image_base"], 16) == coverage.BASE, "Image base mismatch")
    _, baseline, _ = coverage.load_baseline()
    inventory = {coverage.address(f["address"]): f for f in baseline["functions"]
                 if f["domain"] == "native"}
    compare = coverage.pe_comparer(coverage.DEFAULT_BINARY)
    require(compare is not None, "Exact original PE required for this normalization")
    functions = []
    for source in evidence["functions"]:
        # Rename the existing complete tool envelope; never synthesize counts,
        # pages, cursor completion, instruction lines or bytes.
        row = {"addr": source["addr"], "size": source["size"],
               "disassembly": copy.deepcopy(source["disasm"]),
               "originalBytes": source["originalBytes"],
               "pseudocode": copy.deepcopy(source["decompile"])}
        require(row["disassembly"] == source["disasm"] and
                row["originalBytes"] == source["originalBytes"], "Lossy body mapping")
        complete, addresses, reason = coverage.body_assembly(row)
        require(complete, reason)
        start = coverage.va(row["addr"])
        require(start in inventory and row["size"] == inventory[start]["size"],
                "Function extent differs from frozen inventory")
        require(all(start <= a < start + row["size"] for a in addresses),
                "Instruction outside function extent")
        spans = coverage.original_spans(row)
        require(len(spans) == 1 and spans[0][0] == start and
                len(spans[0][1]) == row["size"] and compare(*spans[0]),
                "Original PE body mismatch")
        require(coverage.has_raw_code(row, start, row["size"]), "Missing raw code")
        functions.append(row)
    by_address = {f["addr"]: f for f in functions}
    require(len(functions) == len(by_address) == report["coverage"]["full_bodies"] == 19,
            "Unexpected or duplicate bodies")
    header = {"schema": 1, "domain": "native", "imageBase": evidence["image_base"],
              "originalSha256": evidence["original_sha256"],
              "derivedFrom": {name: PINS[name] for name in ("evidence.json", "report.json")},
              "scope": "Schema adaptation of frozen evidence only; no new analysis or claims of completeness."}
    normalized = dict(header, functions=functions)
    claims = []

    def claim(source, addr, finding, supporting=()):
        require(addr in by_address, "Claim has no captured function")
        refs = [f"coverage-evidence.json#functions[addr={a}]"
                for a in dict.fromkeys((addr, *supporting))]
        for a in (addr, *supporting):
            require(a in by_address, "Supporting body missing")
        claims.append({"addr": addr, "Finding": finding, "Evidence": refs,
                       "Limitations": " ".join(x for x in (source.get("limit"), LIMIT) if x),
                       "sourceFindingId": source["id"],
                       "sourceSummary": source["summary"]})

    for source in report["findings"]:
        kind = source["id"]
        if "function" in source:
            extra = {"rebind_shared": ("0x1403c06b0",),
                     "rebind_new": ("0x1403c0280",)}.get(kind, ())
            finding = " ".join(x for x in (source["summary"], source.get("boundary")) if x)
            claim(source, source["function"], finding, extra)
        elif kind == "park_restore":
            # Split the already recorded two-function observation by owner.
            require(source["functions"] == ["0x1403a80e0", "0x1403a8140"],
                    "Parking source changed")
            claim(source, source["functions"][0],
                  "Moves CurrentPlayer to global RVA 0x2A11268 and clears CurrentPlayer.")
            claim(source, source["functions"][1],
                  "Copies the parked pointer from global RVA 0x2A11268 back to CurrentPlayer "
                  "and clears the parked global. OffCurrent alone is not retirement evidence.",
                  (source["functions"][0],))
        elif kind == "direct_current_stores":
            require(len(source["functions"]) == len(source["stores"]) == 5,
                    "Unexpected direct-store mapping")
            for addr, store in zip(source["functions"], source["stores"]):
                _, addresses, _ = coverage.body_assembly(by_address[addr])
                require(int(store, 16) in addresses, "Direct store belongs to another body")
                claim(source, addr, f"The instruction at {store} directly stores CurrentPlayer "
                      "(global RVA 0x2A105D0). It is one of the five direct stores in the "
                      "recorded 186 direct IDA xrefs; this does not exclude aliased writes.")
        elif kind == "window_pointer_candidates":
            for addr, store in zip(source["functions"], source["stores"]):
                _, addresses, _ = coverage.body_assembly(by_address[addr])
                require(int(store, 16) in addresses, "Window store belongs to another body")
                claim(source, addr, "Allocates and constructs a WINDOW_BALLOON object, then "
                      f"stores that window pointer at receiver+0x5c0 at {store}. "
                      "The receiving object's role remains unresolved.")
        else:
            raise ValueError("Unmapped frozen finding: " + kind)
    require(len(claims) == 16 and len({c["addr"] for c in claims}) == 13,
            "Unexpected claim mapping")
    claim_doc = dict(header, claims=claims)
    products = {"coverage-evidence.json": encoded(normalized), "claims.json": encoded(claim_doc)}
    manifest = {
        "schema": 1, "status": "frozen_schema_normalization",
        "sourceFiles": {name: {"bytes": len(data), "sha256": sha(data)}
                        for name, data in source_bytes.items()},
        "normalizer": {"path": "normalize.py", "sha256": sha(Path(__file__).read_bytes())},
        "coverageParser": {"path": str(parser_path.relative_to(ROOT)).replace("\\", "/"),
                           "sha256": sha(parser_path.read_bytes()), "modified": False},
        "derivedFiles": {name: {"bytes": len(data), "sha256": sha(data)}
                         for name, data in products.items()},
        "validation": {"status": "PASS", "functions": len(functions),
                       "instructions": sum(f["disassembly"]["instruction_count"] for f in functions),
                       "originalBodyBytes": sum(f["size"] for f in functions),
                       "claimOccurrences": len(claims), "claimFunctionAddresses": 13,
                       "checks": ["frozen input SHA256", "unchanged ASM envelopes and original bytes",
                                  "existing parser accepts complete ASM metadata",
                                  "frozen native inventory extent matches",
                                  "all body bytes match exact original PE",
                                  "function-specific claims and supporting bodies resolve"],
                       "coverageRegenerationRun": False},
        "command": "py -3 -B docs/research/actor-binding-writers-20261008/normalize.py --check",
        "limits": LIMIT,
    }
    products["manifest.json"] = encoded(manifest)
    return products


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    products = derive()
    for name, data in products.items():
        path = HERE / name
        if args.check:
            require(path.read_bytes() == data, "Derived artifact differs: " + name)
        else:
            path.write_bytes(data)
    # Resolve using the actual parser against the written, deterministic files.
    coverage, _ = load_coverage()
    for claim in json.loads(products["claims.json"])["claims"]:
        for reference in claim["Evidence"]:
            resolved = coverage.resolve_reference(HERE / "claims.json", reference)
            require(resolved["status"] == "exists" and "selectedAddress" in resolved,
                    "Coverage reference does not resolve")
    print("PASS: 19 bodies / 1281 instructions / 6368 PE bytes; 16 claims on 13 functions; "
          + ("derived files byte-identical" if args.check else "derived files written"))


if __name__ == "__main__":
    main()
