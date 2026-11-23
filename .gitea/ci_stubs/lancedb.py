"""
CI-only stand-in for lancedb.

requirements.txt installs lancedb only where platform_machine is "arm64"
(Apple Silicon), so the x86_64 Gitea Actions runner has no lancedb at all —
and the real native extension needs AVX2, which the runner's virtualized CPU
lacks (SIGILL). The plugin itself imports lancedb lazily and runs without it;
this stub exists so tests/test_search_ranking.py can `import lancedb`. Its
VectorStore tests detect the stub (no __version__) and skip.

The workflow puts this directory on PYTHONPATH so it shadows any real
package in CI only; local development can use the real lancedb.
"""


def connect(*args, **kwargs):
    raise RuntimeError(
        "lancedb is stubbed in CI — tests must not touch a real vector store"
    )
