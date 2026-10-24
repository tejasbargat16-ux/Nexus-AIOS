"""
Packages Tool (Phase 2 Placeholder).

TODO (Phase 2):
- Implement check_package(name).
- Implement install_package(name) via apt / pkg.
- Implement update_system().
- Permission policy: check: allow, install/update: confirm, purge: deny/confirm.
"""

from typing import Any


def install_package(name: str) -> dict[str, Any]:
    """Install OS package."""
    raise NotImplementedError("Packages tool will be implemented in Phase 2.")
