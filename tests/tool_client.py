"""Synthetic client migration to explicit revisions and logical request IDs."""

import uuid
from hermes_muse.contracts import CAS, CREATES
from hermes_muse.mutations import target, object_state
from hermes_muse.views import Views


def arguments(runtime, action, data):
    data = dict(data or {})
    if action in CAS or action in CREATES:
        data.setdefault("request_id", uuid.uuid4().hex)
    if (
        action in CAS
        or action == "interest_record"
        and data.get("id")
        and Views(runtime.home).record("interest", data["id"])
    ):
        kind, key = target(action, data)
        if action == "source_check":
            with runtime.store.transaction() as db:
                key, _, _ = runtime.service.source_identity(data, db)
        if action == "interest_record":
            kind, key = "interest", data["id"]
        try:
            current = object_state(Views(runtime.home), kind, key)[2]
        except ValueError:
            current = "absent"
        data.setdefault("expected_revision", current)
    return data


def record(action, result):
    """Test-only evidence, never installed plugin telemetry or payload logging."""
    import os
    from pathlib import Path
    import json

    evidence = os.environ.get("MUSE_EVIDENCE_DIR")
    if not evidence:
        return
    consume(result)
    row = {
        "backend": "docker" if os.environ.get("MUSE_TEST_DOCKER") == "1" else "local",
        "suite": os.environ.get("MUSE_TEST_SUITE", "native"),
        "action": action,
        "ok": result.get("ok"),
        "code": result.get("code"),
    }
    with (Path(evidence) / "logs/native-action-calls.jsonl").open("a") as stream:
        stream.write(json.dumps(row) + "\n")


_containers = {}


def _container():
    import atexit
    import uuid
    from hermes_constants import get_hermes_home
    from tools.environments.docker import DockerEnvironment

    home = str(get_hermes_home())
    if home not in _containers:
        if not _containers:
            atexit.register(close_containers)
        env = DockerEnvironment(
            image="public.ecr.aws/docker/library/node:22-bookworm-slim",
            cwd="/workspace",
            timeout=30,
            task_id="muse-matrix-" + uuid.uuid4().hex,
            volumes=[],
            forward_env=[],
            env={},
            network=False,
            persistent_filesystem=False,
            persist_across_processes=False,
            image_pinned=True,
        )
        _containers[home] = (env, env._container_id)
    return _containers[home][0]


def transport(envelope):
    """Synthetic model JSON generation in a real container; registry remains on host."""
    import os, json, shlex

    if os.environ.get("MUSE_TEST_DOCKER") != "1":
        return envelope
    out = _container().execute(
        "node -e "
        + shlex.quote("console.log(JSON.stringify(" + json.dumps(envelope) + "))")
    )
    assert out.get("returncode", 0) == 0, out
    return json.loads(out["output"].strip().splitlines()[-1])


def consume(result):
    import os, json, shlex

    if os.environ.get("MUSE_TEST_DOCKER") != "1":
        return
    script = (
        "const result="
        + json.dumps(result)
        + ';if(typeof result.ok!=="boolean")process.exit(1);console.log("accepted")'
    )
    out = _container().execute("node -e " + shlex.quote(script))
    assert out.get("returncode", 0) == 0, out


def close_containers():
    if not _containers:
        return
    import subprocess, json

    for env, cid in _containers.values():
        env.cleanup(force_remove=True)
        assert env.wait_for_cleanup(timeout=30)
        assert (
            subprocess.run(["docker", "inspect", cid], capture_output=True).returncode
            != 0
        )
    print(
        json.dumps(
            {
                "container_matrix_cleanup": True,
                "containers": len(_containers),
                "muse_mounts_added": 0,
                "network": False,
            }
        ),
        flush=True,
    )
    _containers.clear()
