"""Run the shipped Desktop plugin against unchanged installed host SDK sources.

Requires HERMES_SOURCE, MUSE_TEST_URL (tests/ui_host.py), TMPDIR, and a host
node_modules tree. MUSE_SDK_DEPS may supply missing test dependencies; they are
linked read-only into the scratch fixture, never installed into the host/repo.
"""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

source = Path(os.environ["HERMES_SOURCE"])
root = Path(__file__).resolve().parents[1]
assert os.environ.get("TMPDIR")
with tempfile.TemporaryDirectory(prefix="muse-sdk-") as temporary:
    base = Path(temporary)
    for relative in ("apps/desktop/src", "apps/shared"):
        shutil.copytree(
            source / relative,
            base / relative,
            ignore=shutil.ignore_patterns("node_modules", "dist"),
        )
    for relative in ("apps/desktop/vitest.setup.ts", "apps/desktop/package.json"):
        shutil.copy2(source / relative, base / relative)
    shutil.copy2(root / "tests/desktop_sdk.test.mjs", base / "desktop_sdk.test.mjs")
    (base / "muse/desktop").mkdir(parents=True)
    shutil.copy2(root / "desktop/plugin.js", base / "muse/desktop/plugin.js")
    target = base / "node_modules"
    target.mkdir()
    trees = [source / "node_modules"]
    if os.environ.get("MUSE_SDK_DEPS"):
        trees.append(Path(os.environ["MUSE_SDK_DEPS"]) / "node_modules")
    for tree in trees:
        for entry in tree.iterdir():
            if entry.name.startswith("@") and entry.is_dir():
                scope = target / entry.name
                scope.mkdir(exist_ok=True)
                for package in entry.iterdir():
                    dest = scope / package.name
                    if dest.is_symlink():
                        dest.unlink()
                    if not dest.exists():
                        dest.symlink_to(package, target_is_directory=package.is_dir())
            else:
                dest = target / entry.name
                if dest.is_symlink():
                    dest.unlink()
                if not dest.exists():
                    dest.symlink_to(entry, target_is_directory=entry.is_dir())
    aliases = {
        "@hermes/plugin-sdk": str(base / "apps/desktop/src/sdk/index.ts"),
        "@hermes/shared/billing": str(base / "apps/shared/src/billing-types.ts"),
        "@hermes/shared": str(base / "apps/shared/src"),
        "@host": str(base / "apps/desktop/src"),
        "@muse": str(base / "muse"),
        "@": str(base / "apps/desktop/src"),
        "react": str(target / "react"),
        "react-dom": str(target / "react-dom"),
    }
    config = {
        "root": str(base),
        "cacheDir": str(base / "cache"),
        "resolve": {"alias": aliases},
        "test": {
            "environment": "jsdom",
            "include": ["desktop_sdk.test.mjs"],
            "setupFiles": ["./apps/desktop/vitest.setup.ts"],
            "testTimeout": 30000,
        },
    }
    (base / "vitest.config.mjs").write_text(
        "export default " + json.dumps(config) + ";"
    )
    hashes = {
        relative: hashlib.new("sha256", (source / relative).read_bytes()).hexdigest()
        for relative in (
            "apps/desktop/src/sdk/index.ts",
            "apps/desktop/src/contrib/plugin.ts",
            "apps/desktop/src/api/plugins.ts",
            "apps/desktop/src/sdk/composer.ts",
        )
    }
    print(
        json.dumps(
            {"unchanged_host_sources": hashes, "runtime_dependencies_added": False}
        ),
        flush=True,
    )
    result = subprocess.run(
        [
            str(source / "node_modules/.bin/vitest"),
            "run",
            "--config",
            str(base / "vitest.config.mjs"),
            "--configLoader",
            "runner",
        ],
        env=os.environ,
        cwd=base,
    )
    raise SystemExit(result.returncode)
