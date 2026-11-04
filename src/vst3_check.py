"""Run the Steinberg VST3 validator in a bounded child process."""
import argparse
import json
import subprocess
from process import run
from pathlib import Path


def check(validator: Path, plugin: Path) -> dict:
    for path in (validator, plugin):
        if not path.exists():
            return {"ok": False, "error": f"path unavailable: {path}"}
    try:
        result = run(
            [str(validator.resolve()), str(plugin.resolve())],
            capture_output=True, text=True, errors="replace", timeout=45,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "validator timed out after 45 seconds"}
    except OSError as error:
        return {"ok": False, "error": str(error)}
    return {"ok": result.returncode == 0, "exit_code": result.returncode,
            "report": result.stdout, "diagnostics": result.stderr}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validator", type=Path, required=True)
    parser.add_argument("plugin", type=Path)
    args = parser.parse_args()
    result = check(args.validator, args.plugin)
    print(json.dumps(result))
    raise SystemExit(0 if result["ok"] else 1)
