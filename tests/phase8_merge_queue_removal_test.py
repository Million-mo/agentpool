"""Test that merge_queue_into_iterator raises ImportError.

Regression test for structured concurrency migration:
- merge_queue_into_iterator should no longer be importable
- Trying to import it should raise ImportError
"""

from __future__ import annotations

import pytest

from agentpool.utils.streams import async_tee, stream_to_queue, buffer_stream


def test_merge_queue_into_iterator_raises_import_error() -> None:
    """Verify merge_queue_into_iterator import raises ImportError.

    Regression test for structured concurrency migration:
    - merge_queue_into_iterator was removed in Phase 4
    - Attempting to import should raise ImportError
    - Other stream utilities should still work
    """
    with pytest.raises(ImportError):
        from agentpool.utils.streams import merge_queue_into_iterator

    # Verify other utilities still work
    assert callable(async_tee)
    assert callable(stream_to_queue)
    assert callable(buffer_stream)
