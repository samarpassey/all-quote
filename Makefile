.PHONY: setup test test-live run dashboard app intake export export-registry

setup:
	uv sync
	uv run playwright install chromium

test:
	uv run --no-sync pytest -q

test-live:  # the browser-driven executor tests; needs a stable local Chrome
	uv run --no-sync pytest -q -m live_browser

run:
	uv run --no-sync python -m allquote.planner run --route $(ROUTE)

app:
	uv run --no-sync python -m allquote.app

dashboard:
	uv run --no-sync python -m allquote.dashboard

intake:
	uv run --no-sync python -m allquote.intake serve

export-registry:
	uv run --no-sync python -m allquote.registry export

export:
	uv run --no-sync python -m allquote.registry export --with-report
