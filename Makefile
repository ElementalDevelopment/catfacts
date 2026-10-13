.PHONY: run test check import
run:
	python3 -m source.server
test:
	python3 -m unittest discover -s tests -v
check: test
	python3 -m compileall -q source scripts
import:
	python3 scripts/catalog.py wikipedia
