.PHONY: setup test run dashboard intake export export-registry

setup:
	uv sync
	uv run playwright install chromium

test:
	uv run --no-sync pytest -q

run:
	uv run --no-sync python -m allquote.planner run --route $(ROUTE)

dashboard:
	uv run --no-sync python -m allquote.dashboard

intake:
	uv run --no-sync python -m allquote.intake serve

export-registry:
	uv run --no-sync python -m allquote.registry export

export:
	uv run --no-sync python -m allquote.registry export --with-report
