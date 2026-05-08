from __future__ import annotations

import os
from pathlib import Path

import pytest

from mlb_app.server import resolve_static_target
from mlb_app.wsgi import _serve_static


def test_resolve_static_target_rejects_symlink_escape(tmp_path: Path) -> None:
    public = tmp_path / "public"
    outside = tmp_path / "outside"
    public.mkdir()
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    link = public / "leak.txt"
    try:
        link.symlink_to(outside / "secret.txt")
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is not supported on this platform")

    assert resolve_static_target(public, "/leak.txt") is None


def test_resolve_static_target_allows_normal_public_asset(tmp_path: Path) -> None:
    public = tmp_path / "public"
    public.mkdir()
    asset = public / "app.js"
    asset.write_text("console.log('ok')", encoding="utf-8")

    assert resolve_static_target(public, "/app.js") == asset.resolve()


def test_wsgi_static_helper_returns_403_for_path_escape(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    public = tmp_path / "public"
    outside = tmp_path / "outside"
    public.mkdir()
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    link = public / "leak.txt"
    try:
        link.symlink_to(outside / "secret.txt")
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is not supported on this platform")

    import mlb_app.wsgi as wsgi

    monkeypatch.setattr(wsgi, "public_root", public.resolve())
    status, _headers, body = _serve_static("/leak.txt")
    assert status == 403
    assert body == b"Forbidden"
