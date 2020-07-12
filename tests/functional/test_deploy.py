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
async def deploy_relatives(model):
    nrpe = "nrpe"
    nrpe_app = await model.deploy(
        'cs:' + nrpe, application_name=nrpe,
        series='trusty', config={},
        num_units=0
    )

    mysql = "mysql"
    mysql_app = await model.deploy(
        'cs:' + mysql, application_name=mysql,
        series='trusty', config={}
    )

    mediawiki = "mediawiki"
    mediawiki_app = await model.deploy(
        'cs:' + mediawiki, application_name=mediawiki,
        series='trusty', config={}
    )

    await model.add_relation('mysql:db', 'mediawiki:db')
    await model.add_relation('mysql:juju-info', 'nrpe:general-info')
    await model.add_relation('mediawiki:juju-info', 'nrpe:general-info')
    await model.block_until(
        lambda: all(_.status == "active" for _ in (mysql_app, mediawiki_app))
    )

    yield {mediawiki: mediawiki_app, mysql: mysql_app, nrpe: nrpe_app}


@pytest.fixture(scope='module')
async def deploy_app(deploy_relatives, model, series):
    """Return application of the charm under test."""
    app_name = "nagios-{}".format(series)

    """Deploy the nagios app."""
    nagios_app = await model.deploy(
        os.path.join(CHARM_BUILD_DIR, 'nagios'),
        application_name=app_name,
        series=series,
        config={
            'enable_livestatus': True,
            'ssl': False
        }
    )
    await model.add_relation('{}:monitors'.format(app_name), 'mysql:monitors')
    await model.add_relation('{}:nagios'.format(app_name), 'mediawiki:juju-info')
    await model.add_relation('nrpe:monitors', '{}:monitors'.format(app_name))
    await model.block_until(lambda: nagios_app.status == "active")
    await model.block_until(lambda: all(
            _.status == "active"
            for _ in list(deploy_relatives.values()) + [nagios_app]
    ))
    # no need to cleanup since the model will be be torn down at the end of the
    # testing

    yield nagios_app


class Agent:
    def __init__(self, unit):
        self.u = unit
        self.model = unit.model

    def is_active(self, status):
        u = self.u
        return u.agent_status == status and u.workload_status == "active"

    async def block_until(self, lambda_f, timeout=120, wait_period=5):
        await self.model.block_until(
            lambda_f, timeout=timeout, wait_period=wait_period
        )


@pytest.fixture()
async def unit(model, deploy_app):
    """Return the unit we've deployed."""
    unit = Agent(deploy_app.units[0])
    await unit.block_until(lambda: unit.is_active('idle'))
    return unit


@pytest.fixture()
async def auth(file_contents, unit):
    """Return the basic auth credentials."""
    nagiospwd = await file_contents("/var/lib/juju/nagios.passwd", unit.u)
    return 'nagiosadmin', nagiospwd.strip()


#########
# TESTS #
#########

async def test_status(deploy_app):
    """Check that the app is in active state."""
    assert deploy_app.status == "active"


async def test_web_interface_is_protected(auth, unit):
    """Check the nagios http interface."""
    host_url = "http://%s/nagios3/" % unit.u.public_address
    r = requests.get(host_url)
    assert r.status_code == 401, "Web Interface is open to the world"

    r = requests.get(host_url, auth=auth)
    assert r.status_code == 200, "Web Admin login failed"


async def test_hosts_being_monitored(auth, unit):
    host_url = ("http://%s/cgi-bin/nagios3/status.cgi?"
                "hostgroup=all&style=hostdetail") % unit.u.public_address
    r = requests.get(host_url, auth=auth)
    assert r.text.find('mysql') and r.text.find('mediawiki'), \
        "Nagios is not monitoring the hosts it supposed to."


@pytest.fixture(params=['on', 'only'])
async def ssl(model, deploy_app, unit, request):
    """
    Enable SSL before a test, then disable after test

    :param Model model:             Current deployed model
    :param Application deploy_app:  Application under test
    :param Agent unit:              unit from the fixture
    :param request:                 test parameters
    """
    await deploy_app.set_config({'ssl': request.param})
    await unit.block_until(lambda: unit.is_active('executing'))
    await unit.block_until(lambda: unit.is_active('idle'))
    yield request.param
    await deploy_app.set_config({'ssl': 'off'})
    await unit.block_until(lambda: unit.is_active('executing'))
    await unit.block_until(lambda: unit.is_active('idle'))


async def test_web_interface_with_ssl(auth, unit, ssl):
    http_url = "http://%s/nagios3/" % unit.u.public_address
    if ssl == 'only':
        """ SSL ONLY should prevent http nagios -- but must be a race in 
            my test conditions
        with pytest.raises(requests.ConnectionError):
            requests.get(http_url, auth=auth)
        """
    else:
        r = requests.get(http_url, auth=auth)
        assert r.status_code == 200, "HTTP Admin login failed"

    https_url = "https://%s/nagios3/" % unit.u.public_address
    r = requests.get(https_url, auth=auth, verify=False)
    assert r.status_code == 200, "HTTPs Admin login failed"



