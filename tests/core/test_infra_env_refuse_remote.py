"""A-N9 (P59C): infra.env._is_local()/refuse_remote() used to read only the
netloc and the `host` query parameter -- libpq itself also honors
`hostaddr` and `service` (a service file can name an entirely different
host), so a URL carrying either routed around the guard completely. Fixed
by refusing outright whenever either parameter is present, before
resolved_host()'s own opinion is even asked (see infra/env.py's own C23
docstring for why "refuse outright" was chosen over reimplementing that
slice of libpq's DSN resolution).

Pure-function tests -- no database, no LEDGEX_ALLOW_REMOTE_DB set.
"""
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

import infra.env as env  # noqa: E402


def _unset_allow_remote(monkeypatch):
    monkeypatch.delenv("LEDGEX_ALLOW_REMOTE_DB", raising=False)


def test_hostaddr_param_is_refused_even_with_local_host(monkeypatch):
    """A-N9's exact bypass shape: `host` names something the guard would
    call local, but `hostaddr` (which libpq actually prioritizes) points
    somewhere else entirely -- must refuse, not trust `host`."""
    _unset_allow_remote(monkeypatch)
    url = "postgresql://user@localhost/db?hostaddr=203.0.113.5"
    assert env._is_local(url) is False


def test_service_param_is_refused():
    url = "postgresql://user@localhost/db?service=some_remote_profile"
    assert env._is_local(url) is False


def test_hostaddr_without_host_is_refused():
    url = "postgresql://user@/db?hostaddr=203.0.113.5"
    assert env._is_local(url) is False


def test_plain_local_url_still_allowed():
    """Sanity: the fix does not turn every URL into a refusal."""
    assert env._is_local("postgresql://localhost/db") is True
    assert env._is_local("postgresql://user@/db?host=/tmp") is True


def test_refuse_remote_raises_for_hostaddr(monkeypatch):
    _unset_allow_remote(monkeypatch)
    try:
        env.refuse_remote("postgresql://user@localhost/db?hostaddr=203.0.113.5")
        assert False, "refuse_remote did not raise for a hostaddr-bearing URL"
    except SystemExit:
        pass


def test_allow_remote_env_var_still_overrides(monkeypatch):
    """The escape hatch (LEDGEX_ALLOW_REMOTE_DB=1) still works for a
    hostaddr/service URL -- refuse-outright is a default, not an
    unconditional block."""
    monkeypatch.setenv("LEDGEX_ALLOW_REMOTE_DB", "1")
    env.refuse_remote("postgresql://user@localhost/db?hostaddr=203.0.113.5")  # must not raise
