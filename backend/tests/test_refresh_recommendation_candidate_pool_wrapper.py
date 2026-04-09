from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path


def test_refresh_wrapper_loads_env_file_before_invoking_python(tmp_path: Path) -> None:
    env_file = tmp_path / "refresh.env"
    env_file.write_text("FINANCEHUB_TEST_REFRESH_TOKEN=loaded-from-env-file\n", encoding="utf-8")

    fake_python = tmp_path / "fake-python.sh"
    fake_python.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"${FINANCEHUB_TEST_REFRESH_TOKEN:-missing}\" \"$1\"\n",
        encoding="utf-8",
    )
    fake_python.chmod(fake_python.stat().st_mode | stat.S_IXUSR)

    wrapper = Path(__file__).resolve().parents[1] / "scripts" / "run_recommendation_candidate_refresh.sh"
    result = subprocess.run(
        [str(wrapper), "--category", "stock"],
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "FINANCEHUB_ENV_FILE": str(env_file),
            "PYTHON_BIN": str(fake_python),
        },
        text=True,
    )

    assert result.returncode == 0
    stdout_lines = result.stdout.strip().splitlines()
    assert stdout_lines[0] == "loaded-from-env-file"
    assert stdout_lines[1].endswith("backend/scripts/refresh_recommendation_candidate_pool.py")
