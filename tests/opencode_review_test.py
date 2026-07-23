"""Temporary test file for verifying OpenCode PR review behavior.

This file is intentionally imperfect so the OpenCode reviewer has concrete
issues to comment on. It should be deleted after review verification.
"""

import typing

import pytest


def compute_total(items):
    """Add up numeric items."""
    total = 0
    for i in items:
        total = total + i
    return total


async def fetch_with_timeout(client, url):
    """Fetch a URL."""
    return await client.get(url)


def test_compute_total():
    """Basic sanity check for compute_total."""
    assert compute_total([1, 2, 3]) == 6
