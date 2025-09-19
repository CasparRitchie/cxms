# Makefile at repo root

SHELL := /bin/bash

# ---- Defaults ----
APP ?= cxms
MSG ?= $(shell git status --short | head -n 1 | sed 's/^...//')
MSG ?= update
BRANCH := $(shell git rev-parse --abbrev-ref HEAD)
HEROKU := $(shell command -v heroku 2>/dev/null)

.PHONY: deploy push-all status switch logs build-logs open releases \
        ship-main ship-main-stream heroku-plugin-check

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

# Streams the latest build only if heroku-builds plugin exists
build-logs:
	@if [ -z "$(HEROKU)" ]; then echo "Heroku CLI not found."; exit 1; fi
	@if ! heroku plugins | grep -q 'heroku-builds'; then \
	  echo "heroku-builds plugin not installed. Install with: heroku plugins:install heroku-builds"; \
	  exit 1; \
	fi
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

# ---- Plugin-free one-shot ship to main (waits on releases)
ship-main:
	@if [ -z "$(HEROKU)" ]; then echo "Heroku CLI not found."; exit 1; fi
	@echo "Step 1/6 Commit & push current branch ($(BRANCH))"; \
	git add -A; \
	if [ -n "$$(git diff --cached --name-only)" ]; then \
	  git commit -m "$(MSG)"; \
	  git push origin $(BRANCH); \
	else \
	  echo "Nothing to commit on $(BRANCH)"; \
	fi; \
	echo "Step 2/6 Merge $(BRANCH) -> main"; \
	CUR=$(BRANCH); \
	git checkout main; \
	git pull --ff-only origin main || true; \
	git merge --no-edit $$CUR || true; \
	echo "Step 3/6 Push main"; \
	git push origin main; \
	echo "Step 4/6 Capture current latest release number…"; \
	BASE_REL=$$(heroku releases --app $(APP) --json | python -c 'import sys,json; r=json.load(sys.stdin); print(r[0]["version"] if r else 0)'); \
	echo "Current latest release: v$$BASE_REL"; \
	echo "Step 5/6 Wait for a NEW release and success status…"; \
	for i in $$(seq 1 120); do \
	  DATA=$$(heroku releases --app $(APP) --json); \
	  NEW_VER=$$(python - <<'PY'\nimport sys,json\nr=json.load(sys.stdin)\nprint(r[0]['version'] if r else 0)\nPY\n <<<"$$DATA"); \
	  STATUS=$$(python - <<'PY'\nimport sys,json\nr=json.load(sys.stdin)\nprint((r[0].get('status') or '').lower() if r else '')\nPY\n <<<"$$DATA"); \
	  echo "Release v$$NEW_VER status: $$STATUS"; \
	  if [ "$$NEW_VER" -gt "$$BASE_REL" ] && { [ "$$STATUS" = "succeeded" ] || [ "$$STATUS" = "success" ] || [ "$$STATUS" = "completed" ]; }; then \
	    echo "New release v$$NEW_VER succeeded."; \
	    break; \
	  fi; \
	  sleep 5; \
	done; \
	echo "Step 6/6 Opening app & tailing logs…"; \
	heroku open --app $(APP); \
	heroku logs --tail --app $(APP)

# ---- Streamed build version (requires heroku-builds plugin)
ship-main-stream:
	@if [ -z "$(HEROKU)" ]; then echo "Heroku CLI not found."; exit 1; fi
	@if ! heroku plugins | grep -q 'heroku-builds'; then \
	  echo "heroku-builds plugin not installed."; \
	  echo "Install with: heroku plugins:install heroku-builds"; \
	  exit 1; \
	fi
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
	echo "Step 4/7 Wait for new build then stream output…"; \
	PREV=$$(heroku builds --app $(APP) --json | python -c 'import sys,json; d=json.load(sys.stdin); print(d[0]["id"] if d else "")'); \
	for i in $$(seq 1 120); do \
	  LATEST=$$(heroku builds --app $(APP) --json | python -c 'import sys,json; d=json.load(sys.stdin); print(d[0]["id"] if d else "")'); \
	  if [ -n "$$LATEST" ] && [ "$$LATEST" != "$$PREV" ]; then \
	    echo "New build $$LATEST detected — streaming…"; \
	    heroku builds:output --app $(APP) --build $$LATEST || true; \
	    break; \
	  fi; \
	  echo "…waiting for build ($$i)"; sleep 5; \
	done; \
	echo "Step 5/7 Wait for successful release…"; \
	for i in $$(seq 1 120); do \
	  STATUS=$$(heroku releases --app $(APP) --json | python -c 'import sys,json; r=json.load(sys.stdin); print((r[0].get(\"status\") or \"\").lower() if r else \"\")'); \
	  echo "Latest release status: $$STATUS"; \
	  if [ "$$STATUS" = "succeeded" ] || [ "$$STATUS" = "success" ] || [ "$$STATUS" = "completed" ]; then break; fi; \
	  sleep 5; \
	done; \
	echo "Step 6/7 Opening app…"; \
	heroku open --app $(APP); \
	echo "Step 7/7 Tailing runtime logs (Ctrl+C to exit)"; \
	heroku logs --tail --app $(APP)
