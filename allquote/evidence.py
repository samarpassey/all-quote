"""Evidence store. See PLAN.md Task 4.

Will expose `save_evidence(route_id, kind, payload)`: redacts via
allquote.redact, writes to data/evidence/, hashes, and inserts an
allquote.schemas.EvidenceRecord index row. No other module writes into
data/evidence/.
"""
