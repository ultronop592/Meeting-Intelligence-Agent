.PHONY: eval eval-calibrate eval-validate test up down build clean help

help:
	@echo "Meeting Intelligence Agent Commands:"
	@echo "  make eval           Run the evaluation benchmark harness across test meetings"
	@echo "  make eval-calibrate Run LLM Judge calibration across 30 human-labeled samples"
	@echo "  make eval-validate  Validate schemas and formatting of all dataset JSON files"
	@echo "  make up             Start backend and frontend stack with docker compose"
	@echo "  make down           Stop containerized stack"
	@echo "  make build          Build backend and frontend container images"
	@echo "  make test           Run backend pytest test suite"

eval:
	python -m eval.run_eval

eval-calibrate:
	python -m eval.metrics.judge_calibration

eval-validate:
	python -m eval.validate_dataset

test:
	pytest Backend/tests -v

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down
