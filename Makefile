SHELL := /bin/sh
.SHELLFLAGS := -eu -c
.DEFAULT_GOAL := install

UV ?= uv
ARGS ?=

.PHONY: help sync install uninstall test check build run doctor status scan-dry scan-developer-dry apps analyze purge-scan developer-caches-dry completion-print ui web clean

help: ## Show available commands
	@printf "DeepClean Python/uv workflow\n\n"
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-24s %s\n", $$1, $$2}'

sync: ## Create/update the uv environment and lock file
	$(UV) sync --all-groups

install: ## Install into the current user's uv tool directory; never uses sudo
	./install.sh

uninstall: ## Remove the uv-managed command
	./uninstall.sh

test: ## Run Python tests
	$(UV) run pytest

check: test ## Compile, test and smoke-check the package
	$(UV) run python -m compileall -q src/deepclean
	$(UV) run deepclean --version
	$(UV) run deepclean --help >/dev/null

build: ## Build wheel and source distribution
	$(UV) build

run: ## Run the CLI; example: make run ARGS="doctor"
	$(UV) run deepclean $(ARGS)

doctor: ## Run diagnostics
	$(UV) run deepclean doctor

status: ## Show system status
	$(UV) run deepclean status

scan-dry: ## Safe read-only scan
	$(UV) run deepclean scan --profile safe --scan-only $(ARGS)

scan-developer-dry: ## Read-only developer-profile scan
	$(UV) run deepclean scan --profile developer --scan-only $(ARGS)

apps: ## Inventory installed applications
	$(UV) run deepclean apps $(ARGS)

analyze: ## Analyze a path
	$(UV) run deepclean analyze $(ARGS)

purge-scan: ## Read-only project artifact scan
	$(UV) run deepclean purge $(ARGS)

developer-caches-dry: ## Read-only package-manager cache scan
	$(UV) run deepclean developer-caches --scan-only $(ARGS)

completion-print: ## Print shell completion
	$(UV) run deepclean completion $(or $(SHELL_NAME),zsh) --print

ui web: ## Launch the local Web UI
	$(UV) run deepclean ui $(ARGS)

clean: ## Remove only local Python build/test artifacts
	rm -rf build dist .pytest_cache src/deepclean.egg-info
