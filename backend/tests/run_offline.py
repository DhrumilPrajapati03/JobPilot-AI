"""Run the regression suite without loading developer .env credentials.

From backend: python tests/run_offline.py [pytest arguments]
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic_settings.sources import DotEnvSettingsSource

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    with tempfile.TemporaryDirectory(prefix="jobdots-test-files-") as files, patch.dict(os.environ, {
        "APP_ENV": "test", "DEBUG": "false", "EXECUTION_MODE": "inline",
        # Only the throwaway database from scripts/check_database.py; never a real one.
        "DATABASE_URL": os.environ.get("JOBDOTS_TEST_DATABASE_URL", ""), "FILE_STORAGE_DIR": files,
        # No model calls in the offline suite: point Ollama at a closed local port unless a
        # live local-model test is requested (JOBDOTS_TEST_OLLAMA=1).
        **({} if os.environ.get("JOBDOTS_TEST_OLLAMA") else {"OLLAMA_BASE_URL": "http://127.0.0.1:9"}),
    }), patch.object(DotEnvSettingsSource, "__call__", return_value={}):
        raise SystemExit(pytest.main(sys.argv[1:] or ["tests", "-q"]))
