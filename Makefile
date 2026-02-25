.PHONY: lint typecheck pyright

typecheck:
	python -m mypy ascetic_ddd/

pyright:
	pyright

lint: typecheck pyright
