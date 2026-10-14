"""Execute native smoke scripts with a scratch bootstrap before host imports."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile

os.environ["HERMES_DATA_DIR_SUFFIX"] = "-muse-isolated-test"
assert os.environ.get("TMPDIR"), "Set TMPDIR to an isolated scratch directory"
source = os.environ["HERMES_SOURCE"]
root = Path(__file__).resolve().parents[1]
logs = Path(os.environ["MUSE_EVIDENCE_DIR"]) / "logs"
with tempfile.TemporaryDirectory(prefix="muse-native-bootstrap-") as home:
    env = {
        **os.environ,
        "HERMES_HOME": home,
        "HERMES_SOURCE": source,
        "PYTHONPATH": str(root) + os.pathsep + source,
        "HERMES_IGNORE_USER_CONFIG": "1",
        "HERMES_DISABLE_LAZY_INSTALLS": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    failures = 0
    for name in sys.argv[1:]:
        assert Path(name).name in {
            "native_smoke.py",
            "native_views_smoke.py",
            "native_new_contracts.py",
            "native_docker_smoke.py",
            "official_validation.py",
        }, "Run native_smoke for its helper suites"
        with (
            logs
            / (
                Path(name).stem
                + ("-docker" if os.environ.get("MUSE_TEST_DOCKER") == "1" else "")
                + ".txt"
            )
        ).open("w") as log:
            result = subprocess.run(
                [sys.executable, str(root / name)],
                env={**env, "MUSE_TEST_SUITE": Path(name).stem},
                cwd=root,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        print(name, result.returncode, flush=True)
        failures += result.returncode != 0
    raise SystemExit(bool(failures))
