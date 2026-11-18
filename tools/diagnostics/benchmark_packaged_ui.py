"""Run packaged UI scenarios on a private Windows desktop with copied databases."""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def copy_data(source, target):
    for name in ("history.sqlite3", "statistics.sqlite3"):
        path = source / "ccz_fast_data" / name
        if not path.is_file():
            raise FileNotFoundError(path)
        destination = target / "ccz_fast_data" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path.resolve().as_uri()+"?mode=ro", uri=True)) as original, \
                closing(sqlite3.connect(destination)) as copied:
            original.backup(copied)
    rules = source / "random_rules_v2.json"
    if rules.is_file():
        shutil.copy2(rules, target / rules.name)
    fixture = ROOT/'tests/fixtures/personnel_220_1104/randomized-result.json'
    shutil.copy2(fixture, target/'recorded-ui-result.json')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--trace-tk", action="store_true", help="Include Tk command timing (diagnostic overhead)")
    args = parser.parse_args()
    from tests.helpers.desktop import background_desktop
    executable = args.exe.resolve()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ccz-packaged-ui-") as folder:
        base = Path(folder)
        copy_data(args.base, base)
        request = base / "request.json"
        report_path = base / "report.json"
        command = [str(executable)]
        if args.source:
            command.append(str(ROOT / "fast_randomizer.py"))
        with background_desktop() as startup:
            request.write_text(json.dumps(dict(base=str(base), output=str(report_path),
                desktop=startup.lpDesktop if startup is not None else "default", trace_tk=args.trace_tk)), encoding="utf-8")
            process = subprocess.Popen([*command, "--benchmark-ui", str(request)],
                cwd=base, startupinfo=startup, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                code = process.wait(timeout=180)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                raise TimeoutError("Packaged UI benchmark exceeded 180 seconds") from None
        if not report_path.is_file():
            raise RuntimeError(f"EXE exited with {code} without a report")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        with executable.open("rb") as stream:
            report["executable_sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        if code or report["status"] != "passed":
            raise RuntimeError(f"UI scenarios failed; inspect {output}")


if __name__ == "__main__":
    main()
