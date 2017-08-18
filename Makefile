#!/usr/bin/make
PYTHON := /usr/bin/python3
export PYTHONPATH := hooks

default:
	echo Nothing to do

# Primitive test runner. Someone please fix this.
test:
	tests/00-setup
	tests/100-deploy
	tests/10-initial-test
	tests/15-nrpe-test
	tests/20-ssl-test
	tests/21-monitors-interface-test
	tests/22-extraconfig-test
	tests/23-livestatus-test
	tests/24-pagerduty-test

bin/charm_helpers_sync.py:
	@mkdir -p bin
	@bzr cat lp:charm-helpers/tools/charm_helpers_sync/charm_helpers_sync.py \
        > bin/charm_helpers_sync.py

sync: bin/charm_helpers_sync.py
	@$(PYTHON) bin/charm_helpers_sync.py -c charm-helpers.yaml


