.PHONY: eval test up down build clean help

help:
	@echo "Meeting Intelligence Agent Commands:"
	@echo "  make eval       Run the evaluation benchmark harness and generate report"
	@echo "  make up         Start backend and frontend stack with docker compose"
	@echo "  make down       Stop containerized stack"
	@echo "  make build      Build backend and frontend container images"
	@echo "  make test       Run backend pytest test suite"

eval:
	python -m eval.run_eval

test:
	pytest Backend/tests -v

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down
