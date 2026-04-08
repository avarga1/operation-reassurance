"""
Streamlit GUI dashboard.

Run with: streamlit run reassure/gui/app.py -- --path ./my-repo

Sections:
  - Overview: health score, LOC breakdown, language pie
  - Test Coverage: per-symbol heatmap, coverage by type
  - Observability: dark modules treemap
  - Dead Code: list with confidence badges
  - SOLID Health: god file/class/function rankings, dependency graph
  - Churn Hotspots: scatter plot of complexity vs churn
"""

import streamlit as st
from pathlib import Path


def main() -> None:
    st.set_page_config(
        page_title="Reassure — Repo Health",
        page_icon="🔍",
        layout="wide",
    )

    st.title("🔍 operation-reassurance")
    st.caption("Repo health observatory. CST/AST-powered, no runtime required.")

    # Sidebar: repo path input + analyzer toggles
    with st.sidebar:
        repo_path = st.text_input("Repository path", value=".")
        st.divider()
        run_coverage = st.checkbox("Test Coverage", value=True)
        run_observability = st.checkbox("Observability", value=True)
        run_dead_code = st.checkbox("Dead Code", value=True)
        run_solid = st.checkbox("SOLID Health", value=True)
        run_metrics = st.checkbox("Metrics", value=True)
        analyze = st.button("Analyze", type="primary", use_container_width=True)

    if not analyze:
        st.info("Configure a repo path and hit **Analyze** to get started.")
        return

    # TODO: run analysis pipeline and render each section
    # st.spinner while running
    # Tabs: Overview | Coverage | Observability | Dead Code | SOLID | Metrics
    raise NotImplementedError


if __name__ == "__main__":
    main()
