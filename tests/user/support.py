"""Shared helpers for the user-profile tests."""
from jk.user import profile
from tests.support import call


def run_profile(*argv: str) -> tuple[int, str, str]:
    """Run the `profile` command in-process; (status, stdout, stderr)."""
    return call(profile.main, *argv)
