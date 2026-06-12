"""
CI-only stand-in for lancedb.

The real lancedb native extension requires AVX2 and dies with SIGILL
("Fatal Python error: Illegal instruction") on the Gitea Actions runner's
virtualized CPU. The test suite never exercises lancedb — every test that
reaches the vector-store chain patches VectorStoreManager — it only needs
`import lancedb` to succeed.

The workflow puts this directory on PYTHONPATH so it shadows the real
package in CI only; local development uses the real lancedb.
"""


def connect(*args, **kwargs):
    raise RuntimeError(
        "lancedb is stubbed in CI — tests must not touch a real vector store"
    )
