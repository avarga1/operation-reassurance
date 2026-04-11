"""
FastAPI backend for the reassure GUI.

Thin HTTP wrapper over the Python analyzers — no business logic here,
just transport. The analyzers themselves are unchanged.

Endpoints:
  POST /analyze          — run one or more analyzers against a repo path
  POST /blast-radius     — run blast radius analysis against a git diff
  GET  /config           — read .reassure.toml from a repo path
  PUT  /config           — write .reassure.toml to a repo path
  GET  /symbol-map       — return all symbols in a repo
  GET  /health           — liveness check

Run:
  uvicorn reassure.api.server:app --reload --port 7474
"""

from __future__ import annotations

import subprocess
import traceback
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from reassure.analyzers.observability import ObservabilityAnalyzer
from reassure.analyzers.test_coverage import CoverageAnalyzer
from reassure.core.repo_walker import walk_repo

try:
    from reassure.analyzers.blast_radius import analyze_blast_radius, get_diff, parse_diff

    _HAS_BLAST_RADIUS = True
except ImportError:
    _HAS_BLAST_RADIUS = False

try:
    from reassure.analyzers.solid import SolidAnalyzer

    _HAS_SOLID = True
except ImportError:
    _HAS_SOLID = False

app = FastAPI(title="reassure", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_ANALYZERS: dict[str, Any] = {
    "coverage": CoverageAnalyzer(),
    "observability": ObservabilityAnalyzer(),
}
if _HAS_SOLID:
    _ANALYZERS["solid"] = SolidAnalyzer()


# ── Request / response models ─────────────────────────────────────────────────


class AnalyzeRequest(BaseModel):
    path: str
    analyzers: list[str] = ["coverage", "observability", "solid"]


class BlastRadiusRequest(BaseModel):
    path: str
    base: str = "main"
    transitive_depth: int = 2


class ConfigWriteRequest(BaseModel):
    path: str
    config: dict[str, Any]


# ── Endpoints ─────────────────────────────────────────────────────────────────


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": "0.2.0"}


@app.post("/analyze")
def analyze(req: AnalyzeRequest) -> dict:
    root = _resolve(req.path)
    index = walk_repo(root)

    results: dict[str, Any] = {
        "path": str(root),
        "files": len(index.files),
        "symbols": len(index.all_symbols),
        "test_files": len(index.test_files),
        "languages": _lang_breakdown(index),
        "analyzers": {},
    }

    for name in req.analyzers:
        analyzer = _ANALYZERS.get(name)
        if analyzer is None:
            results["analyzers"][name] = {"error": f"Unknown analyzer: {name}"}
            continue
        try:
            result = analyzer.analyze(index)
            results["analyzers"][name] = {
                "summary": result.summary,
                "issues": result.issues,
            }
        except Exception as e:
            results["analyzers"][name] = {"error": str(e), "trace": traceback.format_exc()}

    return results


@app.post("/blast-radius")
def blast_radius(req: BlastRadiusRequest) -> dict:
    if not _HAS_BLAST_RADIUS:
        raise HTTPException(
            status_code=501, detail="blast_radius analyzer not available in this build"
        )
    root = _resolve(req.path)

    try:
        diff_text = get_diff(root, req.base)
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=400, detail=f"git diff failed: {e.stderr}") from e

    if not diff_text.strip():
        return {
            "summary": f"No changes vs {req.base}",
            "base": req.base,
            "affected_symbols": [],
            "uncovered_callers": [],
        }

    index = walk_repo(root)
    diff_hunks = parse_diff(diff_text, root)
    report = analyze_blast_radius(
        index, diff_hunks, base=req.base, transitive_depth=req.transitive_depth
    )

    return {
        "summary": (
            f"{len(report.affected_symbols)} symbols changed, "
            f"{report.total_callers} callers, "
            f"{report.total_uncovered_callers} uncovered"
        ),
        "base": report.base,
        "has_risk": report.has_risk,
        "affected_symbols": [
            {
                "name": a.symbol.name,
                "kind": a.symbol.kind,
                "file": str(a.symbol.file.relative_to(root)),
                "line_start": a.symbol.line_start,
                "line_end": a.symbol.line_end,
                "lang": a.symbol.lang,
                "direct_callers": [
                    {
                        "name": c.symbol.name,
                        "file": str(c.file.relative_to(root)),
                        "line": c.symbol.line_start,
                        "covered": c.is_covered,
                    }
                    for c in a.direct_callers
                ],
                "transitive_callers": [
                    {
                        "name": c.symbol.name,
                        "file": str(c.file.relative_to(root)),
                        "line": c.symbol.line_start,
                        "covered": c.is_covered,
                    }
                    for c in a.transitive_callers
                ],
                "uncovered_caller_count": len(a.uncovered_callers),
            }
            for a in report.affected_symbols
        ],
        "uncovered_callers": [
            {
                "changed_symbol": a.symbol.name,
                "caller": c.symbol.name,
                "caller_file": str(c.file.relative_to(root)),
                "caller_line": c.symbol.line_start,
            }
            for a in report.affected_symbols
            for c in a.uncovered_callers
        ],
    }


@app.get("/symbol-map")
def symbol_map(path: str, lang: str | None = None) -> dict:
    root = _resolve(path)
    index = walk_repo(root)
    symbols = [
        {
            "name": s.name,
            "kind": s.kind,
            "file": str(s.file.relative_to(root)),
            "line": s.line_start,
            "lang": s.lang,
            "parent_class": s.parent_class,
            "is_public": s.is_public,
        }
        for s in index.all_symbols
        if lang is None or s.lang == lang
    ]
    return {"total": len(symbols), "symbols": symbols}


@app.get("/config")
def get_config(path: str) -> dict:
    root = _resolve(path)
    config_path = root / ".reassure.toml"
    if not config_path.exists():
        return {"exists": False, "config": _default_config()}
    try:
        import tomllib

        with open(config_path, "rb") as f:
            config = tomllib.load(f)
        return {"exists": True, "config": config}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read config: {e}") from e


@app.put("/config")
def put_config(req: ConfigWriteRequest) -> dict:
    root = _resolve(req.path)
    config_path = root / ".reassure.toml"
    try:
        import tomli_w

        with open(config_path, "wb") as f:
            tomli_w.dump(req.config, f)
        return {"written": True, "path": str(config_path)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write config: {e}") from e


# ── Helpers ───────────────────────────────────────────────────────────────────


def _resolve(path: str) -> Path:
    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {path}")
    return root


def _lang_breakdown(index: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for f in index.source_files:
        counts[f.lang] = counts.get(f.lang, 0) + 1
    return counts


def _default_config() -> dict:
    return {
        "thresholds": {
            "god_file_loc": 500,
            "god_file_functions": 20,
            "god_file_classes": 5,
            "god_class_methods": 15,
            "blast_radius_depth": 2,
        },
        "ignore": [],
        "analyzers": {"custom": []},
    }
