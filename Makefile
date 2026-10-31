.PHONY: eval eval-live eval-calibrate eval-validate eval-phase6 eval-phase7 test up down build clean help

help:
	@echo "Meeting Intelligence Agent Commands:"
	@echo "  make eval           Run evaluation benchmark harness across test meetings"
	@echo "  make eval-live      Execute live multi-agent pipeline and score predictions"
	@echo "  make eval-calibrate Run LLM Judge calibration across 30 human-labeled samples"
	@echo "  make eval-validate  Validate schemas and formatting of all dataset JSON files"
	@echo "  make eval-phase6    Run Phase 6 chunk retrieval benchmark (recall@k, MRR, citations)"
	@echo "  make eval-phase7    Run Phase 7 differentiator benchmark (commitments, contradictions, Hinglish)"
	@echo "  make up             Start backend and frontend stack with docker compose"
	@echo "  make down           Stop containerized stack"
	@echo "  make build          Build backend and frontend container images"
	@echo "  make test           Run backend pytest test suite"

eval:
	python -m eval.run_eval

eval-live:
	python -m eval.run_eval --live

eval-calibrate:
	python -m eval.metrics.judge_calibration

eval-validate:
	python -m eval.validate_dataset

eval-phase6:
	python -m eval.phase6_retrieval_eval --top-k 5 --output eval/results/phase6.json

eval-phase7:
	python -m eval.phase7_differentiator_eval --output eval/results/phase7.json

test:
	pytest Backend/tests -v

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down
