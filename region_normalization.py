from __future__ import annotations

import re
from typing import Any


_UNITED_STATES_PATTERN = re.compile(
    r"(?:\bunited\s+states(?:\s+of\s+america)?\b|\bu\.?s\.?(?:a\.?)?\b|美国)",
    re.IGNORECASE,
)


def normalize_region_label(value: Any) -> str:
    """Return a stable region label while leaving intentional taxonomy intact."""
    text = str(value or "").strip()
    if not text:
        return ""
    # Location-shaped US values such as "Boston, USA" belong to the same
    # portfolio bucket as the existing Chinese label "美国".  Do not flatten
    # other hierarchical labels (for example "欧洲-英国") because those may be
    # deliberate research categories.
    if _UNITED_STATES_PATTERN.search(text):
        return "美国"
    return text
