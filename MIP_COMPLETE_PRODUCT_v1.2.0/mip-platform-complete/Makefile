.PHONY: install test lint typecheck demo api clean

install:
	python -m pip install -e ".[dev]"

test:
	pytest --cov=mip --cov-report=term-missing --cov-fail-under=80

lint:
	ruff check src tests
	ruff format --check src tests

typecheck:
	mypy src/mip

demo:
	mip analyze examples/sample-mainframe --db data/demo.db --output output/demo
	mip stats --db data/demo.db
	mip roots --db data/demo.db

api:
	mip serve --db data/demo.db --host 0.0.0.0 --port 8000

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov output/demo data/demo.db
