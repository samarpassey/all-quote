.PHONY: setup test run dashboard export export-registry

setup:
	uv sync
	uv run playwright install chromium

test:
	pytest -q

run:
	uv run --no-sync python -m allquote.planner run --route $(ROUTE)

dashboard:
	uv run --no-sync streamlit run allquote/dashboard.py

export-registry:
	uv run --no-sync python -m allquote.registry export

export:
	uv run --no-sync python -m allquote.registry export --with-report
