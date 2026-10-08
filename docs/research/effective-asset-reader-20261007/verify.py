"""Verify this implementation receipt, without importing or executing repository source."""
import sys
sys.dont_write_bytecode = True
import hashlib
import json
from pathlib import Path


def main():
    here = Path(__file__).resolve().parent
    root = here.parents[2]
    manifest = json.loads((here / "fingerprints.json").read_text(encoding="utf-8"))
    checks = []
    for entry in manifest["files"]:
        path = root / entry["path"]
        safe = not Path(entry["path"]).is_absolute() and ":" not in entry["path"] and ".." not in Path(entry["path"]).parts
        safe = safe and path.resolve().is_relative_to(root.resolve())
        data = path.read_bytes() if safe and path.is_file() else b""
        checks.append({"check": entry["path"], "passed": safe and path.is_file()
                       and len(data) == entry["bytes"] and hashlib.sha256(data).hexdigest() == entry["sha256"]})
    report = json.loads((here / "report.json").read_text(encoding="utf-8"))
    log = (here / "core-tests.txt").read_text(encoding="utf-8-sig")
    test = report["verification"]
    checks += [
        {"check": "test receipt", "passed": f'{test["passed"]} passed, 0 failed.' in log and not any(line.startswith("FAIL ") for line in log.splitlines())},
        {"check": "targeted test count", "passed": sum(line.startswith("PASS effective assets:") for line in log.splitlines()) == test["newEffectiveReaderChecks"]},
        {"check": "only offline binding", "passed": report["bindingStrength"] == "OfflineManifestBinding" and report["nativeEvidence"]["newNativeClaims"] == 0},
    ]
    output = {"success": all(c["passed"] for c in checks), "checks": checks}
    (here / "verification.json").write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"success": output["success"], "passed": sum(c["passed"] for c in checks), "failed": sum(not c["passed"] for c in checks)}))
    return 0 if output["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
