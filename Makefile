venv:
	python3 -m venv .venv

install:
	pip install -r requirements.txt

compile:
	python -m compileall .

test:
	pytest

build:
	python library_pipeline.py
