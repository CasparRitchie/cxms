# Makefile at repo root

SHELL := /bin/bash

# ---- Defaults ----
APP ?= cxms                      # <— your Heroku app
MSG ?= $(shell git status --short | head -n 1 | sed 's/^...//')
MSG ?= update
BRANCH := $(shell git rev-parse --abbrev-ref HEAD)
HEROKU := $(shell command -v heroku 2>/dev/null)

.PHONY: deploy push-all status switch logs build-logs open releases ship-main

# ---- Deploy current branch ----
deploy:
	git add -A
	@if [ -z "$$(git diff --cached --name-only)" ]; then \
	  echo "Nothing to commit"; \
	else \
	  echo "Committing: $(MSG)"; \
	  git commit -m "$(MSG)"; \
	  echo "Pushing branch: $(BRANCH)"; \
	  git push origin $(BRANCH); \
	fi

# ---- Push ALL local branches ----
push-all:
	git add -A
	@if [ -n "$$(git diff --cached --name-only)" ]; then \
	  echo "Committing: $(MSG)"; \
	  git commit -m "$(MSG)"; \
	else \
	  echo "Nothing to commit"; \
	fi
	@for branch in $$(git for-each-ref --format='%(refname:short)' refs/heads/); do \
	  echo "Pushing $$branch..."; \
	  git push origin $$branch; \
	done

status:
	git status

# Usage: make switch b=main
switch:
	@if [ -z "$(b)" ]; then echo "Usage: make switch b=<branch>"; else git checkout $(b); fi

# ---- Heroku helpers ----
logs:
	@if [ -z "$(HEROKU)" ]; then echo "Heroku CLI not found."; exit 1; fi
	heroku logs --tail --app $(APP)

build-logs:
	@if [ -z "$(HEROKU)" ]; then echo "Heroku CLI not found."; exit 1; fi
	@LATEST=$$(heroku builds --app $(APP) --json | python -c 'import sys,json; d=json.load(sys.stdin); print(d[0]["id"] if d else "")'); \
	if [ -z "$$LATEST" ]; then echo "No builds found for $(APP)."; exit 1; fi; \
	echo "Streaming build $$LATEST for $(APP) ..."; \
	heroku builds:output --app $(APP) --build $$LATEST

open:
	@if [ -z "$(HEROKU)" ]; then echo "Heroku CLI not found."; exit 1; fi
	heroku open --app $(APP)

releases:
	@if [ -z "$(HEROKU)" ]; then echo "Heroku CLI not found."; exit 1; fi
	heroku releases --app $(APP)

# ---- One-shot ship to main + watch ----
ship-main:
	@if [ -z "$(HEROKU)" ]; then echo "Heroku CLI not found."; exit 1; fi
	@echo "Step 1/7 Commit & push current branch ($(BRANCH))"; \
	git add -A; \
	if [ -n "$$(git diff --cached --name-only)" ]; then \
	  git commit -m "$(MSG)"; \
	  git push origin $(BRANCH); \
	else \
	  echo "Nothing to commit on $(BRANCH)"; \
	fi; \
	echo "Step 2/7 Merge $(BRANCH) -> main"; \
	CUR=$(BRANCH); \
	git checkout main; \
	git pull --ff-only origin main || true; \
	git merge --no-edit $$CUR || true; \
	echo "Step 3/7 Push main"; \
	git push origin main; \
	echo "Step 4/7 Wait for GitHub/Heroku build to appear…"; \
	PREV_BUILD=$$(heroku builds --app $(APP) --json | python -c 'import sys,json; d=json.load(sys.stdin); print(d[0]["id"] if d else "")'); \
	for i in $$(seq 1 60); do \
	  LATEST=$$(heroku builds --app $(APP) --json | python -c 'import sys,json; d=json.load(sys.stdin); print(d[0]["id"] if d else "")'); \
	  if [ "$$LATEST" != "$$PREV_BUILD" ] && [ -n "$$LATEST" ]; then \
	    echo "New build $$LATEST detected — streaming output…"; \
	    heroku builds:output --app $(APP) --build $$LATEST || true; \
	    break; \
	  fi; \
	  echo "…waiting for build ($$i)"; sleep 5; \
	done; \
	echo "Step 5/7 Wait for successful release…"; \
	for i in $$(seq 1 60); do \
	  STATUS=$$(heroku releases --app $(APP) --json | python -c 'import sys,json; r=json.load(sys.stdin); print((r[0].get("status") or "").lower() if r else "")'); \
	  echo "Latest release status: $$STATUS"; \
	  if [ "$$STATUS" = "succeeded" ] || [ "$$STATUS" = "success" ] || [ "$$STATUS" = "completed" ]; then \
	    break; \
	  fi; \
	  sleep 5; \
	done; \
	echo "Step 6/7 Opening app…"; \
	heroku open --app $(APP); \
	echo "Step 7/7 Tailing runtime logs (Ctrl+C to exit)"; \
	heroku logs --tail --app $(APP)
