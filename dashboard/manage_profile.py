"""Private subprocess entry; HTTP authentication stays in the host-mounted router."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hermes_muse.profile_admin import operate

if __name__ == '__main__':
    try:
        result = operate(json.load(sys.stdin))
        print(json.dumps({'ok': True, 'result': result}, ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({'ok': False, 'code': getattr(exc, 'code', 'source_unavailable'), 'error': str(exc)}, ensure_ascii=False))
        raise SystemExit(1)
