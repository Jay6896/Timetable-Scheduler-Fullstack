"""
Shim module for Differential Evolution.

This file previously mixed UI (Dash) with the algorithm and had syntax errors.
All Dash UI has been moved into `Dash_UI.py` and mounted from `app.py`.

To keep imports working (e.g., `from differential_evolution import DifferentialEvolution`),
we re-export the algorithm from `differential_evolution_api` here.
"""

from __future__ import annotations

# Re-export the algorithm so existing imports continue to work
from differential_evolution_api import DifferentialEvolution  # noqa: F401

__all__ = ["DifferentialEvolution"]


def _main() -> None:
    """Optional standalone entry (no UI)."""
    import sys
    print(
        "DifferentialEvolution shim is loaded.\n"
        "- Use the Flask API endpoints to run optimization.\n"
        "- Dash UI is now in Dash_UI.py and served under /interactive/.\n"
        "- For direct usage: `from differential_evolution import DifferentialEvolution`.",
        file=sys.stderr,
    )


if __name__ == "__main__":
    _main()