"""Test package: every test run gets its own throw-away JOBKIT_HOME, so no test can touch real data."""
import atexit
import os
import shutil
import tempfile

REAL_HOME = os.environ.get("JOBKIT_HOME") or os.path.join(os.path.expanduser("~"), ".jobkit")   # read-only checks only
_HOME = tempfile.mkdtemp(prefix="jobkit-test-home-")
os.environ["JOBKIT_HOME"] = _HOME
atexit.register(shutil.rmtree, _HOME, True)

from jk import store  # noqa: E402  # pylint: disable=wrong-import-position  (after the environment is set)

store.create()
