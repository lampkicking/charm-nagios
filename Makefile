#!/usr/bin/make
PYTHON := /usr/bin/python3
export PYTHONPATH := hooks
PROJECTPATH = $(dir $(realpath $(MAKEFILE_LIST)))
METADATA_FILE = "metadata.yaml"
CHARM_NAME = $(shell cat ${PROJECTPATH}/${METADATA_FILE} | grep -E '^name:' | awk '{print $2}')
ifndef CHARM_BUILD_DIR
    CHARM_BUILD_DIR := /tmp/charm-builds
    $(warning Warning CHARM_BUILD_DIR was not set, defaulting to $(CHARM_BUILD_DIR))
endif

default:
	echo Nothing to do

test: lint proof unittest functional
	@echo "Testing charm $(CHARM_NAME)"

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
	@echo Executing functional tests in $(CHARM_BUILD_DIR)
	@CHARM_BUILD_DIR=$(CHARM_BUILD_DIR) \
     PYTEST_KEEP_MODEL=$(PYTEST_KEEP_MODEL) \
	 PYTEST_CLOUD_NAME=$(PYTEST_CLOUD_NAME) \
	 PYTEST_CLOUD_REGION=$(PYTEST_CLOUD_REGION) \
	 tox -e functional

unittest:
	@echo "Running unit tests"
	@tox -e unit

proof:
	@echo "Running charm proof"
	@charm proof

clean:
	@echo "Cleaning files"
	@if [ -d .tox ] ; then rm -r .tox ; fi
	@if [ -d .pytest_cache ] ; then rm -r .pytest_cache ; fi
	@find . | grep -E "\(__pycache__|\.pyc|\.pyo$\)" | xargs rm -rf
	@rm -rf $(CHARM_BUILD_DIR)/$(CHARM_NAME)/*


bin/charm_helpers_sync.py:
	@mkdir -p bin
	@bzr cat lp:charm-helpers/tools/charm_helpers_sync/charm_helpers_sync.py \
        > bin/charm_helpers_sync.py

sync: bin/charm_helpers_sync.py
	@$(PYTHON) bin/charm_helpers_sync.py -c charm-helpers.yaml


