"""Run unit suite with all host globals bound to a disposable scratch home."""

import os
from pathlib import Path
import sys
import tempfile
import unittest

def main():
    os.environ["HERMES_DATA_DIR_SUFFIX"] = "-muse-isolated-test"
    assert os.environ.get("TMPDIR"), "Set TMPDIR to an isolated scratch directory"
    with tempfile.TemporaryDirectory(prefix="muse-unit-") as home:
        os.environ["HERMES_HOME"] = home
        os.environ["HERMES_IGNORE_USER_CONFIG"] = "1"
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        result = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.discover(
                str(Path(__file__).parent), pattern="test_*.py"
            )
        )
        raise SystemExit(not result.wasSuccessful())


if __name__ == "__main__":
    main()
