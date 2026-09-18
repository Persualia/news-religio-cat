PYTHON    ?= .venv/bin/python
LOG_LEVEL ?= INFO
SITES     ?=
LIMIT     ?=

RUN_ARGS := --log-level $(LOG_LEVEL)
ifneq ($(strip $(SITES)),)
RUN_ARGS += --sites $(SITES)
endif
ifneq ($(strip $(LIMIT)),)
RUN_ARGS += --limit-per-site $(LIMIT)
endif

# Empty values are kept by load_dotenv (it never overrides) and read as "unset",
# so the dry run doesn't post to #catalunya-religio.
NO_SLACK := SLACK_WEBHOOK_URL= SLACK_BOT_TOKEN=

.PHONY: run dry

# Real run: creates Trello cards, writes to Google Sheets and notifies Slack.
run:
	PYTHONPATH=src $(PYTHON) scripts/run_daily.py $(RUN_ARGS)

# Scrape only: no Trello, no Sheets, no Slack.
dry:
	$(NO_SLACK) PYTHONPATH=src $(PYTHON) scripts/run_daily.py --dry-run $(RUN_ARGS)
