.PHONY: lint typecheck

typecheck:
	python -m mypy ascetic_ddd/

lint: typecheck
