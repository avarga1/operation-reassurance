"""
Streamlit GUI dashboard.

Run with: make gui

Sections:
  - Overview: health score, file/symbol counts, language breakdown
  - Test Coverage: per-symbol table, coverage by type
  - Observability: dark modules + dark function list
"""

from pathlib import Path

import pandas as pd
import streamlit as st

from reassure.analyzers.observability import analyze_observability
from reassure.analyzers.test_coverage import analyze_coverage
from reassure.classifiers.test_type import classify_test_file
from reassure.core.repo_walker import walk_repo

_IGNORE = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".dart_tool",
    "build",
    "dist",
    "target",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
}


def _file_explorer() -> Path | None:
    """Sidebar repo picker — paste a directory path."""
    raw = st.text_input("Repository path", placeholder="/Users/you/my-repo")
    if not raw:
        return None
    p = Path(raw).expanduser().resolve()
    if not p.is_dir():
        st.error("Not a valid directory.")
        return None
    st.caption(str(p))
    return p


def main() -> None:
    st.set_page_config(
        page_title="Reassure — Repo Health",
        page_icon="🔍",
        layout="wide",
    )

    st.title("🔍 operation-reassurance")
    st.caption("Repo health observatory. CST/AST-powered, no runtime required.")

    with st.sidebar:
        root = _file_explorer()
        st.divider()
        run_coverage = st.checkbox("Test Coverage", value=True)
        run_observability = st.checkbox("Observability", value=True)
        analyze = st.button(
            "Analyze" if root is None else f"Analyze `{root.name}`",
            type="primary",
            use_container_width=True,
            disabled=root is None,
        )

    if root is None or not analyze:
        st.info("Browse to a repo in the sidebar and hit **Analyze**.")
        return

    if not root.is_dir():
        st.error(f"Path not found: `{root}`")
        return

    with st.spinner(f"Walking `{root}` …"):
        index = walk_repo(root)

    # ── Overview ──────────────────────────────────────────────────────────────
    st.subheader("Overview")
    lang_counts: dict[str, int] = {}
    for f in index.files:
        lang_counts[f.lang] = lang_counts.get(f.lang, 0) + 1

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Files", len(index.files))
    col2.metric("Symbols", len(index.all_symbols))
    col3.metric("Test files", len(index.test_files))
    col4.metric("Languages", len(lang_counts))

    if lang_counts:
        lang_df = pd.DataFrame(
            {"Language": list(lang_counts.keys()), "Files": list(lang_counts.values())}
        ).sort_values("Files", ascending=False)
        st.bar_chart(lang_df.set_index("Language"))

    st.divider()

    # ── Test Coverage ─────────────────────────────────────────────────────────
    if run_coverage:
        st.subheader("Test Coverage")
        with st.spinner("Analyzing coverage…"):
            classifications = {
                f.path: classify_test_file(f.path, list(f.imports), []) for f in index.test_files
            }
            cov = analyze_coverage(index, classifications)

        pct = cov.coverage_pct
        color = "normal" if pct >= 80 else "inverse" if pct < 50 else "off"
        c1, c2, c3 = st.columns(3)
        c1.metric("Coverage", f"{pct}%", delta=None, delta_color=color)
        c2.metric("Covered", cov.covered_symbols)
        c3.metric("Uncovered", len(cov.uncovered))

        rows = []
        for sc in cov.symbols:
            rows.append(
                {
                    "Symbol": sc.symbol.name,
                    "Kind": sc.symbol.kind,
                    "File": str(sc.symbol.file.relative_to(root)),
                    "Line": sc.symbol.line_start,
                    "Covered": not sc.is_uncovered,
                    "Unit": bool(sc.tests_by_type.get("unit")),
                    "Integration": bool(sc.tests_by_type.get("integration")),
                    "E2E": bool(sc.tests_by_type.get("e2e")),
                }
            )

        df = pd.DataFrame(rows)
        uncovered_only = st.toggle("Show uncovered only", value=True)
        if uncovered_only:
            df = df[~df["Covered"]]

        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Covered": st.column_config.CheckboxColumn(),
                "Unit": st.column_config.CheckboxColumn(),
                "Integration": st.column_config.CheckboxColumn(),
                "E2E": st.column_config.CheckboxColumn(),
            },
        )
        st.divider()

    # ── Observability ─────────────────────────────────────────────────────────
    if run_observability:
        st.subheader("Observability")
        with st.spinner("Analyzing observability…"):
            obs = analyze_observability(index)

        pct_obs = round(100 - obs.dark_pct, 1)
        o1, o2, o3 = st.columns(3)
        o1.metric("Instrumented", f"{pct_obs}%")
        o2.metric("Dark functions", obs.dark_functions)
        o3.metric("Dark modules", len(obs.dark_module_paths))

        if obs.dark_module_paths:
            st.markdown("**Dark modules** — zero production instrumentation")
            for p in obs.dark_module_paths:
                try:
                    display = p.relative_to(root)
                except ValueError:
                    display = p
                st.markdown(f"- `{display}`")

        if obs.gaps:
            gap_rows = [
                {
                    "Function": g.symbol.name,
                    "Kind": g.symbol.kind,
                    "File": str(g.symbol.file.relative_to(root)),
                    "Line": g.symbol.line_start,
                }
                for g in sorted(obs.gaps, key=lambda g: (g.symbol.file, g.symbol.line_start))
            ]
            with st.expander(f"All {len(obs.gaps)} dark functions"):
                st.dataframe(pd.DataFrame(gap_rows), use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
