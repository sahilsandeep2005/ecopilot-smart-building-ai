.PHONY: install init models test mcp agent dashboard run report

install:
	python -m pip install -r requirements.txt

init:
	python scripts/init_db.py

models:
	python scripts/setup_models.py

test:
	pytest

mcp:
	python -m mcp_server.server

agent:
	python -m agent.orchestrator

dashboard:
	streamlit run dashboard/app.py

run:
	python -m experiments.run_scenarios

report:
	python -m experiments.generate_report
