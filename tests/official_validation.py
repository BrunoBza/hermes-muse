import dataclasses
import json
import os
from pathlib import Path
import sys
import tempfile

os.environ["HERMES_DATA_DIR_SUFFIX"] = "-muse-isolated-test"
assert os.environ.get("TMPDIR"), "Set TMPDIR to an isolated scratch directory"
with tempfile.TemporaryDirectory(prefix="muse-validator-") as home:
    os.environ["HERMES_HOME"] = home
    os.environ["HERMES_IGNORE_USER_CONFIG"] = "1"
    os.environ["HERMES_DISABLE_LAZY_INSTALLS"] = "1"
    os.environ["PYTHONPATH"] = os.environ["HERMES_SOURCE"]
    sys.path.insert(0, os.environ["HERMES_SOURCE"])
    from hermes_cli.plugin_validate import validate_plugin_dir

    report = validate_plugin_dir(Path(__file__).resolve().parents[1])
    print(json.dumps(dataclasses.asdict(report), indent=2, default=str))
    print("passed:", report.ok if hasattr(report, "ok") else "see checks")

    raise SystemExit(not report.ok)
