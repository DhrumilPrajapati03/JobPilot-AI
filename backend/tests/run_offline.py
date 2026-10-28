"""Run the regression suite without loading developer .env credentials.

From backend: python tests/run_offline.py [pytest arguments]
"""
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic_settings.sources import DotEnvSettingsSource

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    with patch.dict(os.environ, {"DEBUG": "false", "EXECUTION_MODE": "inline"}), patch.object(
        DotEnvSettingsSource, "__call__", return_value={}
    ):
        raise SystemExit(pytest.main(sys.argv[1:] or ["tests", "-q"]))
