"""
v2 reader — near-identity pass for manuscript.v2.0 artifacts.

The v2 reader exists to keep the dispatch surface uniform: every
artifact, regardless of source schema, comes out the other side as a
v2.0-shaped dict. For v2.0 input the work is minimal — defensive
shape checks + a top-level dict copy so downstream mutation can't
leak back into the caller's artifact object.

What this reader does NOT do
  - Run the full v2.0 JSON Schema validator. That's a separate concern
    (the producer is responsible for emitting valid artifacts; W2 will
    schema-validate at a different layer if/when the consolidation
    item lands). This reader's job is shape-conformance enough to let
    the converter run.
  - Re-classify, re-validate, or otherwise modify block content. The
    blocks come from W1 v5.0 with their roles already assigned and
    (per I-2) never null.
"""
from __future__ import annotations
from copy import deepcopy
from typing import Any, Dict


REQUIRED_TOP_LEVEL = (
    "schema_version", "artifact_type",
    "source", "processing", "content",
)


def read(artifact: Dict[str, Any]) -> Dict[str, Any]:
    """Defensive copy + minimal shape check for a v2.0 artifact."""
    sv = artifact.get("schema_version")
    if sv != "2.0":
        raise ValueError(f"v2 reader called on schema_version={sv!r}")

    missing = [k for k in REQUIRED_TOP_LEVEL if k not in artifact]
    if missing:
        raise ValueError(
            f"v2.0 artifact missing required top-level field(s): {missing}. "
            f"Producer should not have emitted; check W1 v5.0 emit step."
        )

    blocks = artifact.get("content", {}).get("blocks", [])
    if not isinstance(blocks, list) or not blocks:
        raise ValueError(
            "v2.0 artifact has no content.blocks; refusing to render an "
            "empty manuscript."
        )

    for i, b in enumerate(blocks):
        if not isinstance(b, dict):
            raise ValueError(f"v2.0 block at index {i} is not a dict: {type(b).__name__}")
        if not b.get("role"):
            raise ValueError(
                f"v2.0 block at index {i} (id={b.get('id')!r}) lacks a "
                f"role. I-2 violation in the producer; W1 should have "
                f"applied terminal default before emit."
            )

    # Defensive deep-copy so the converter's mutations don't echo back
    # into the caller's reference. Optional but cheap and tidy.
    return deepcopy(artifact)
