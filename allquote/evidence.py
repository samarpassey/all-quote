"""Evidence record construction. See PLAN.md Task 4 / docs/ARCHITECTURE.md.

`write_evidence_record` is the single place that turns an already-written,
already-redacted artifact on disk into an indexed `EvidenceRecord`: it hashes
the artifact, builds the record, and writes a sidecar JSON beside it. Callers
(executor.py, normalize.py) must write the artifact itself via
`allquote.redact.safe_write_evidence` first — this module never writes
unredacted content and never picks its own write path into data/evidence/.
"""

import hashlib
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from allquote.schemas import EvidenceKind, EvidenceRecord, Provenance


def write_evidence_record(
    *,
    registry_id: str,
    kind: EvidenceKind,
    timestamp: datetime,
    source_url_or_phone: str,
    artifact_path: Path,
    provenance: Provenance,
    fields_disclosed: list[str] = (),
) -> EvidenceRecord:
    """Hashes `artifact_path` (already written and redacted by the caller),
    builds the EvidenceRecord, and writes a `.evidence.json` sidecar beside
    the artifact. Does not itself write or redact the artifact.
    """
    evidence_hash = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    record = EvidenceRecord(
        evidence_id=uuid4().hex,
        registry_id=registry_id,
        kind=kind,
        timestamp=timestamp,
        source_url_or_phone=source_url_or_phone,
        artifact_path=str(artifact_path),
        evidence_hash=evidence_hash,
        redacted=True,
        provenance=provenance,
        fields_disclosed=list(fields_disclosed),
        consent_receipt_id=None,
        retention_deadline=None,
    )
    sidecar_path = artifact_path.with_suffix(artifact_path.suffix + ".evidence.json")
    sidecar_path.write_text(record.model_dump_json(indent=2))
    return record
