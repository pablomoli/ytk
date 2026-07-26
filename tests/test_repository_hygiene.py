import subprocess
from pathlib import Path


def test_retired_dom_environment_is_absent() -> None:
    root = Path(__file__).resolve().parents[1]
    forbidden = ("js" + "dom").encode()
    lock_path = Path("web/pnpm-lock.yaml")
    tracked = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout.split(b"\0")

    offenders = []
    for raw_path in tracked:
        if not raw_path:
            continue
        relative_path = Path(raw_path.decode())
        if relative_path == lock_path:
            continue
        path = root / relative_path
        if path.is_file() and forbidden in path.read_bytes().lower():
            offenders.append(str(path.relative_to(root)))

    assert offenders == []

    lock = (root / lock_path).read_bytes().lower()
    assert b"\n  " + forbidden + b"@" not in lock
    assert b"(" + forbidden + b"@" not in lock
