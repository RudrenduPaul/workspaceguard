"""
Default data directory resolution. Ported from src/core/paths.ts.
"""
from __future__ import annotations

import os


def default_data_dir() -> str:
    """
    Default data directory when neither --data-dir nor
    WORKSPACEGUARD_DATA_DIR is given. This used to default to the current
    working directory, silently writing a live AES-256-GCM master key into
    whatever directory the command happened to be run from -- a real risk
    of dropping (or colliding with) key material in an unrelated project.

    ``~/.workspaceguard`` is stable regardless of cwd. Implemented directly
    with ``os.path.expanduser`` rather than pulling in a cross-platform
    app-data-directory package -- no such dependency exists yet in
    pyproject.toml, and a single flat directory under the user's home is
    enough here (matches src/core/paths.ts's TypeScript twin).
    """
    return os.path.join(os.path.expanduser("~"), ".workspaceguard")
