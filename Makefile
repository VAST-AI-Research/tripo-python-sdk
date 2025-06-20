.PHONY: clean lint format test build publish

clean:
	rm -rf build/ dist/ *.egg-info/ .pytest_cache/ .coverage htmlcov/ .mypy_cache/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

lint:
	flake8 tripo3d
	mypy tripo3d
	black --check tripo3d
	isort --check-only --profile black tripo3d

format:
	black tripo3d
	isort --profile black tripo3d

test:
	pytest -v

test-cov:
	pytest --cov=tripo3d --cov-report=html

build:
	python -m build

publish:
	python -m twine upload dist/*

install-dev:
	pip install -e .
	pip install -r requirements-dev.txt