"""
Observability coverage analyzer.

Detects functions and modules with no logging, tracing, or metrics
instrumentation — purely via static CST analysis.

A function is considered "dark" (unobservable) if its body contains no:
  - Logger calls (logger.info, log.warning, logging.debug, etc.)
  - Trace spans (@trace decorator, tracer.start_span, with tracer.span)
  - Metrics calls (counter.inc, histogram.observe, metrics.record)

Useful for catching entire service layers (e.g. a DB layer) that emit
nothing to your observability stack.
"""

from dataclasses import dataclass
from pathlib import Path

from reassure.core.repo_walker import RepoIndex
from reassure.core.symbol_map import Symbol


@dataclass
class ObservabilityGap:
    symbol: Symbol
    reason: str     # "no logging", "no tracing", "completely dark"


@dataclass
class ObservabilityReport:
    gaps: list[ObservabilityGap]
    total_functions: int
    dark_functions: int

    @property
    def dark_pct(self) -> float:
        if self.total_functions == 0:
            return 0.0
        return round(self.dark_functions / self.total_functions * 100, 1)

    @property
    def dark_modules(self) -> list[Path]:
        """Files where EVERY function is dark."""
        # TODO: implement grouping
        raise NotImplementedError


def analyze_observability(
    index: RepoIndex,
    log_patterns: list[str] | None = None,
    trace_patterns: list[str] | None = None,
    metrics_patterns: list[str] | None = None,
) -> ObservabilityReport:
    """
    Scan all source functions for observability instrumentation.

    Patterns are matched against identifier nodes in the function body CST.
    Configurable via .reassure.toml [observability] section.
    """
    # TODO: implement
    # For each source symbol:
    #   1. Get the function body node from the CST
    #   2. Walk all call_expression / attribute_access nodes in the body
    #   3. Check if any match log/trace/metrics patterns
    #   4. If none match → ObservabilityGap
    raise NotImplementedError
