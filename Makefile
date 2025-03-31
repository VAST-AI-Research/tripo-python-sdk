.PHONY: clean lint format test build publish

clean:
	rm -rf build/ dist/ *.egg-info/ .pytest_cache/ .coverage htmlcov/ .mypy_cache/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

lint:
	flake8 tripo
	mypy tripo
	black --check tripo
	isort --check-only --profile black tripo

format:
	black tripo
	isort --profile black tripo

test:
	pytest -v

test-cov:
	pytest --cov=tripo --cov-report=html

build:
	python -m build

publish:
	python -m twine upload dist/*

install-dev:
	pip install -e .
	pip install -r requirements-dev.txt 