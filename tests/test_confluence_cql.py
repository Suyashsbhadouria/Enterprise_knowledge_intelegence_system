from ekcip_connectors.confluence_cql import (
    bounded_cql_recent,
    is_likely_unbounded,
    resolve_sync_cql,
)


def test_is_likely_unbounded_detects_order_only():
    assert is_likely_unbounded("type=page order by lastModified desc") is True


def test_is_likely_unbounded_accepts_recent_filter():
    assert is_likely_unbounded(bounded_cql_recent()) is False


def test_resolve_sync_cql_replaces_unbounded():
    resolved = resolve_sync_cql("type=page order by lastModified desc", default=bounded_cql_recent())
    assert "lastModified" in resolved
