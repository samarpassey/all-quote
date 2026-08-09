"""Fernet-encrypted vault for sensitive IntakeProfile values. See PLAN.md Task 3.

Will expose `vault.get(field)` and a `vault.inject(callable)` context that
zeroes references after use. Only this module ever holds real sensitive values;
everywhere else sees `allquote.schemas.VaultRef` tokens.
"""
