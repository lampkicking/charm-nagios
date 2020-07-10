#!/usr/bin/python3.6

import os

import pytest

import requests

pytestmark = pytest.mark.asyncio

CHARM_BUILD_DIR = os.getenv("CHARM_BUILD_DIR", "..").rstrip("/")

SERIES = [
    "trusty",
    "xenial",
    "bionic",
]


############
# FIXTURES #
############


@pytest.fixture(scope='module', params=SERIES)
def series(request):
    """Return ubuntu version (i.e. xenial) in use in the test."""
    return request.param


@pytest.fixture(scope='module')
async def deploy_app(model, series):
    """Return application of the charm under test."""
    app_name = "nagios-{}".format(series)

    """Deploy the nagios app."""
    nagios_app = await model.deploy(
        os.path.join(CHARM_BUILD_DIR, 'nagios'),
        application_name=app_name,
        series=series,
        config={'enable_livestatus': True}
    )
    await model.block_until(lambda: nagios_app.status == "active")
    # no need to cleanup since the model will be be torn down at the end of the
    # testing

    yield nagios_app


@pytest.fixture(scope='module')
async def unit(deploy_app):
    """Return the thruk_agent unit we've deployed."""
    return deploy_app.units[0]


#########
# TESTS #
#########

async def test_status(deploy_app):
    """Check that the app is in active state."""
    assert deploy_app.status == "active"


async def test_http(model, file_contents, unit, series):
    """Check the thruk http interface."""
    nagiospwd = await file_contents("/var/lib/juju/nagios.passwd", unit)
    host_url = "http://%s/" % unit.public_address
    auth = 'nagiosadmin', nagiospwd
    requests.get(host_url, auth=auth)
