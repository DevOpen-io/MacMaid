SHELL := /bin/sh
.SHELLFLAGS := -eu -c
.DEFAULT_GOAL := build

CARGO ?= cargo
ARGS ?=

.PHONY: help build build-app dmg install prod-install test check run doctor status scan-dry apps analyze purge-scan ui clean

help: ## Show available commands
	@printf "MacMaid Rust & Native Desktop workflow\n\n"
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-24s %s\n", $$1, $$2}'

build: ## Build Rust workspace (macmaid-core, macmaid-cli, macmaid-ffi)
	$(CARGO) build --release --workspace

build-app: ## Build native macOS desktop application bundle (.app) and CLI
	./scripts/build-macos-app.sh

dmg: build-app ## Create release DMG and CLI package
	./scripts/create-dmg.sh build/macos-app/MacMaid.app build/macos-app/MacMaid.dmg
	tar -C build/macos-app/cli -czf build/macos-app/MacMaid-cli.tar.gz macmaid

install: ## Build and install standalone macOS CLI and Desktop app
	sh scripts/prod-install.sh

prod-install: install ## Alias for install

test: ## Run Rust test suite
	$(CARGO) test --workspace

check: ## Run formatting, clippy quality gates and tests
	$(CARGO) fmt --all -- --check
	$(CARGO) clippy --workspace --all-targets -- -D warnings
	$(CARGO) test --workspace

run: ## Run the CLI; example: make run ARGS="doctor"
	$(CARGO) run -p macmaid-cli -- $(ARGS)

doctor: ## Run diagnostics
	$(CARGO) run -p macmaid-cli -- doctor

status: ## Show system status
	$(CARGO) run -p macmaid-cli -- status

scan-dry: ## Safe read-only scan
	$(CARGO) run -p macmaid-cli -- scan --profile safe --scan-only $(ARGS)

apps: ## Inventory installed applications
	$(CARGO) run -p macmaid-cli -- apps $(ARGS)

analyze: ## Analyze a path
	$(CARGO) run -p macmaid-cli -- analyze $(ARGS)

purge-scan: ## Read-only project artifact scan
	$(CARGO) run -p macmaid-cli -- purge $(ARGS)

ui: ## Launch the native macOS Desktop application
	open build/macos-app/MacMaid.app

clean: ## Remove build artifacts
	$(CARGO) clean
	rm -rf build dist
