"""
Whether semantic search (search_entities) can run on this Mac.

The search index lives in LanceDB, which ships macOS wheels for Apple Silicon
only. requirements.txt skips lancedb on Intel Macs (a platform_machine
marker) so the plugin still installs there; without it the plugin hides
search_entities and serves every other tool. This module is the one place
that decides, and nothing imports lancedb before it has answered.
"""

import functools
import importlib
import platform
import sys
from dataclasses import dataclass
from typing import Callable, Optional

INTEL_MAC_REASON = (
    "Semantic search (search_entities) disabled: LanceDB is not available on "
    "this Mac (requires Apple Silicon). Every other tool works."
)


@dataclass(frozen=True)
class SemanticSearchStatus:
    """Outcome of the availability check."""

    available: bool
    # One user-facing sentence when unavailable; '' when available
    reason: str = ""
    # True when unavailable by design (Intel Mac); False when LanceDB should
    # have loaded but did not (a broken install), which deserves a warning
    expected: bool = False
    # Exception text of a failed import, for the DEBUG log
    detail: str = ""


def detect_semantic_search(
    platform_name: Optional[str] = None,
    machine: Optional[str] = None,
    importer: Callable[[str], object] = importlib.import_module,
) -> SemanticSearchStatus:
    """
    Check whether the vector store's native libraries load.

    On an Intel Mac the import is not even attempted: pip skipped lancedb
    there, and should a copy turn up anyway, its native library can kill the
    interpreter with SIGILL on CPUs without AVX2, which no except clause
    catches. Elsewhere (Apple Silicon, and Linux for development and CI) the
    answer is whether lancedb and pyarrow import.
    """
    platform_name = platform_name if platform_name is not None else sys.platform
    machine = machine if machine is not None else platform.machine()

    if platform_name == "darwin" and machine != "arm64":
        return SemanticSearchStatus(available=False, reason=INTEL_MAC_REASON, expected=True)

    try:
        importer("lancedb")
        importer("pyarrow")
    except Exception as e:  # ImportError, or OSError from a native library
        return SemanticSearchStatus(
            available=False,
            reason=(
                "Semantic search (search_entities) disabled: LanceDB could not "
                "be loaded — reinstall the plugin. Every other tool works."
            ),
            expected=False,
            detail=f"{type(e).__name__}: {e}",
        )
    return SemanticSearchStatus(available=True)


@functools.lru_cache(maxsize=1)
def semantic_search_status() -> SemanticSearchStatus:
    """The availability check, run once per process and then cached."""
    return detect_semantic_search()
