"""Shared plumbing for brief applications."""

from __future__ import annotations


class BriefCoreError(Exception):
    """Base exception for application, transport, and runtime failures."""
