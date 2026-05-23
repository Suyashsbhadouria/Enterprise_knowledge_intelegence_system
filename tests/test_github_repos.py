import pytest

from ekcip_connectors.github_repos import parse_repo_list, resolve_sync_repos


def test_parse_repo_list_accepts_owner_repo():
    assert parse_repo_list("acme/platform, acme/other") == ["acme/platform", "acme/other"]


def test_parse_repo_list_rejects_invalid():
    with pytest.raises(ValueError, match="Invalid GitHub repo"):
        parse_repo_list("not-a-repo")


def test_resolve_sync_repos_uses_default():
    repos = resolve_sync_repos(None, default="acme/app")
    assert repos == ["acme/app"]
