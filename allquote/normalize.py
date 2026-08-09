"""Raw executor output -> QuoteResult; dedupe resolver. See PLAN.md Task 8.

Will map raw outcomes to allquote.schemas.QuoteResult against the coverage
benchmark, and assign/resolve distinct_rate_source_id across routes.
"""
