"""
Golden-query evaluation for search_entities (indigo-mcp-server#72).

Not a unit test (pytest does not collect it): it needs either a live MCP
endpoint or a built search index plus an OpenAI key. Run it before and after
a search change and compare the summary lines.

Live, through any MCP endpoint that exposes search_entities:
    python tests/eval/golden_search.py --mcp URL --token-file FILE [--tool NAME]

Offline, against a local index built by the plugin's VectorStore:
    python tests/eval/golden_search.py --db PATH --openai-key-file FILE

Both modes take --golden FILE: a JSON object of named query sets, each a list
of [query, [acceptable device names]] (see EXAMPLE_GOLDEN). A name may use a
leading/trailing * as a wildcard. Golden sets name a real house's devices,
so keep them out of the repository.
"""

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

# (query, acceptable device names)
EXAMPLE_GOLDEN = {
    "house names": [["living room lamp", ["Living Room Lamp"]]],
    "aliases": [["entryway light", ["Foyer Light"]], ["landscape lighting", ["Outdoor Spotlight*"]]],
}
LIMIT = 50


def matches(name: str, patterns) -> bool:
    lowered = name.lower()
    for pattern in patterns:
        p = pattern.lower()
        if p.startswith("*") and p.endswith("*"):
            if p.strip("*") in lowered:
                return True
        elif p.endswith("*"):
            if lowered.startswith(p[:-1]):
                return True
        elif lowered == p:
            return True
    return False


# ----------------------------------------------------------------------
# Backends: each returns the ranked device names for a query


class McpBackend:
    """Minimal streamable-HTTP MCP client (initialize, then tools/call)."""

    def __init__(self, url: str, token: str, tool: str):
        self.url, self.token, self.tool = url, token, tool
        self.session = None
        self._id = 0
        self._rpc("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "golden-search-eval", "version": "1"},
        })
        self._rpc("notifications/initialized", None, notify=True)

    def _rpc(self, method, params, notify=False):
        body = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            body["params"] = params
        if not notify:
            self._id += 1
            body["id"] = self._id
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {self.token}",
        }
        if self.session:
            headers["Mcp-Session-Id"] = self.session
        req = urllib.request.Request(self.url, data=json.dumps(body).encode(), headers=headers)
        with urllib.request.urlopen(req, timeout=120) as resp:
            self.session = resp.headers.get("Mcp-Session-Id") or self.session
            raw = resp.read().decode()
        if notify or not raw.strip():
            return None
        if raw.lstrip().startswith("{"):
            return json.loads(raw)
        for line in raw.splitlines():  # SSE
            if line.startswith("data:"):
                payload = json.loads(line[5:].strip())
                if payload.get("id") == body.get("id"):
                    return payload
        raise RuntimeError(f"no JSON-RPC reply in: {raw[:200]}")

    def devices(self, query):
        reply = self._rpc("tools/call", {
            "name": self.tool,
            "arguments": {"query": query, "entity_types": ["device"], "limit": LIMIT},
        })
        text = reply["result"]["content"][0]["text"]
        payload = json.loads(text)
        return [d["name"] for d in payload.get("results", {}).get("devices", [])]


class LocalBackend:
    """The plugin's own VectorStore + QueryParser against a local index."""

    def __init__(self, db_path: str, key: str, expand: bool):
        plugin = Path(__file__).resolve().parents[2] / "MCP Advanced Tools.indigoPlugin/Contents/Server Plugin"
        sys.path.insert(0, str(plugin))
        os.environ["OPENAI_API_KEY"] = key
        os.environ.setdefault("SMALL_MODEL", "gpt-6-luna")
        os.environ.setdefault("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large")
        os.environ["LANGSMITH_TRACING"] = "false"
        from mcp_server.common.vector_store.main import VectorStore
        from mcp_server.tools.search_entities.query_parser import QueryParser
        import logging
        self.store = VectorStore(db_path, logger=logging.getLogger("eval"))
        self.parser = QueryParser()
        self.expand = expand

    def devices(self, query):
        expanded = self.parser.expand_query(query) if self.expand else None
        results, _ = self.store.search(
            query, entity_types=["devices"], top_k=LIMIT,
            similarity_threshold=0.0, expanded_query=expanded,
        )
        return [r["name"] for r in results]


# ----------------------------------------------------------------------


def evaluate(backend, golden_sets, verbose=True):
    summary = {}
    for label, golden in golden_sets.items():
        ranks = []
        for query, expected in golden:
            names = backend.devices(query)
            rank = next((i + 1 for i, n in enumerate(names) if matches(n, expected)), None)
            ranks.append(rank)
            if verbose:
                top = names[0] if names else "-"
                print(f"  {label:11} rank {str(rank or f'>{len(names)}'):>4}  {query!r:34} top1={top!r}")
        n = len(ranks)
        top1 = sum(1 for r in ranks if r == 1)
        top3 = sum(1 for r in ranks if r and r <= 3)
        top5 = sum(1 for r in ranks if r and r <= 5)
        mrr = sum(1 / r for r in ranks if r) / n
        summary[label] = (top1, top3, top5, mrr, n)
    print()
    for label, (top1, top3, top5, mrr, n) in summary.items():
        print(f"{label:11} ({n:2}): top1 {top1:2}  top3 {top3:2}  top5 {top5:2}  MRR {mrr:.2f}")
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mcp", help="MCP endpoint URL")
    ap.add_argument("--token-file", help="file holding the endpoint's bearer token")
    ap.add_argument("--tool", default="search_entities", help="tool name at that endpoint")
    ap.add_argument("--db", help="local search index (LanceDB directory)")
    ap.add_argument("--openai-key-file", help="file holding an OpenAI API key (local mode)")
    ap.add_argument("--no-expansion", action="store_true", help="local mode: original words only")
    ap.add_argument("--golden", required=True, help="JSON file of query sets (see module docstring)")
    ap.add_argument("-q", "--quiet", action="store_true")
    args = ap.parse_args()

    if args.mcp:
        token = Path(args.token_file).read_text().strip()
        backend = McpBackend(args.mcp, token, args.tool)
    elif args.db:
        key = Path(args.openai_key_file).read_text().strip()
        backend = LocalBackend(args.db, key, expand=not args.no_expansion)
    else:
        ap.error("give --mcp or --db")
    golden_sets = json.loads(Path(args.golden).read_text())
    evaluate(backend, golden_sets, verbose=not args.quiet)


if __name__ == "__main__":
    main()
