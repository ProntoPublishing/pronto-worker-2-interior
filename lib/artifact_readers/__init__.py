"""
Artifact readers — schema_version dispatcher.

W2 v1.3 reads BOTH manuscript.v1.0 (legacy, currently in production)
and manuscript.v2.0 (forthcoming, when W1 v5.0 ships) artifacts. This
module is the single dispatch point: every consumer of artifact data
goes through `read_artifact()` and gets back a v2.0-shaped artifact
regardless of the input version. Downstream code (converter,
template fill, etc.) only ever sees v2.0 shape.

Internal contract:
  read_artifact(input_artifact: dict) -> NormalizedArtifact

NormalizedArtifact mirrors the v2.0 schema:
  - content.blocks[] : v2.0-shaped blocks (CIR type + role +
    role-specific fields, per Doc 22 v1.0.2)
  - manuscript_meta? : optional {title, subtitle, author}
  - applied_rules[], warnings[], rule_faults[]: as v2.0
  - schema_version, worker_version, etc. preserved or upgraded

The v1 reader is an in-memory upgrader: v1.0 type → v2.0 (CIR_type,
role) plus role-specific fields. The v2 reader is near-identity (input
shape passes through; minor defensive normalization).

Eventually (post-W1-v5.0-deployment-stable, per the corpus testing
plan), W2 v2.0 will drop the v1 reader entirely. v1.3 is the
parallel-reader generation.
"""
from __future__ import annotations
from typing import Any, Dict

from . import v1, v2


SUPPORTED_SCHEMA_VERSIONS = ("1.0", "1.1", "2.0")


class UnsupportedSchemaVersionError(ValueError):
    """Raised when the artifact declares a schema_version this reader
    does not understand. The message names the supported set so an
    operator can see immediately whether a producer drift is to blame.
    """


def read_artifact(artifact: Dict[str, Any]) -> Dict[str, Any]:
    """Validate + parse an artifact of any supported schema version.

    Returns the artifact in v2.0 shape so the rest of W2 sees a single
    representation. The original input is not mutated.
    """
    if not isinstance(artifact, dict):
        raise TypeError(f"artifact must be a dict, got {type(artifact).__name__}")

    sv = artifact.get("schema_version")
    if sv in ("1.0", "1.1"):
        return v1.read(artifact)
    if sv == "2.0":
        return v2.read(artifact)

    raise UnsupportedSchemaVersionError(
        f"Unsupported schema_version: {sv!r}. "
        f"W2 v1.3 reads {SUPPORTED_SCHEMA_VERSIONS}. "
        f"Either the producer is on a future schema (in which case W2 "
        f"needs to ship a parallel-reader for it before consuming) or "
        f"the artifact is malformed."
    )
