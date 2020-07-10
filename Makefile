#!/usr/bin/make
PYTHON := /usr/bin/python3
export PYTHONPATH := hooks
PROJECTPATH = $(dir $(realpath $(MAKEFILE_LIST)))
CHARM_NAME = $(notdir $(PROJECTPATH:%/=%))
ifndef CHARM_BUILD_DIR
    CHARM_BUILD_DIR := /tmp/$(CHARM_NAME)-builds
    $(warning Warning CHARM_BUILD_DIR was not set, defaulting to $(CHARM_BUILD_DIR))
endif

default:
	echo Nothing to do

test: lint unittest functional

lint:
	@echo "Running flake8"
	@tox -e lint

build:
	@echo "Building charm to base directory $(CHARM_BUILD_DIR)/$(CHARM_NAME)"
	@-git describe --tags > ./repo-info
	@mkdir -p $(CHARM_BUILD_DIR)/$(CHARM_NAME)
	@cp -r * $(CHARM_BUILD_DIR)/$(CHARM_NAME)

# Primitive test runner. Someone please fix this.
functional: build
	@PYTEST_KEEP_MODEL=$(PYTEST_KEEP_MODEL) \
	 PYTEST_CLOUD_NAME=$(PYTEST_CLOUD_NAME) \
	 PYTEST_CLOUD_REGION=$(PYTEST_CLOUD_REGION) \
	 tox -e functional

unittest:
	@tox -e unit


bin/charm_helpers_sync.py:
	@mkdir -p bin
	@bzr cat lp:charm-helpers/tools/charm_helpers_sync/charm_helpers_sync.py \
        > bin/charm_helpers_sync.py

sync: bin/charm_helpers_sync.py
	@$(PYTHON) bin/charm_helpers_sync.py -c charm-helpers.yaml


