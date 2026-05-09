from __future__ import annotations

"""Retired legacy data-health handlers.

Sprint 9C moved these endpoints to ``mlb_app.api.routes.data_health`` so
services are resolved once from ``AppContainer`` instead of constructed per
request in the legacy sync router.
"""
