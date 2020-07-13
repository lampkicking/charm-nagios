from async_generator import asynccontextmanager
import pytest
import requests
pytestmark = pytest.mark.asyncio


@asynccontextmanager
async def config(unit, item, test_value, post_test):
    await unit.application.set_config({item: test_value})
    await unit.block_until_or_timeout(lambda: unit.is_active('executing'))
    await unit.block_until(lambda: unit.is_active('idle'))
    yield test_value
    await unit.application.set_config({item: post_test})
    await unit.block_until_or_timeout(lambda: unit.is_active('executing'))
    await unit.block_until(lambda: unit.is_active('idle'))


@pytest.fixture(params=['on', 'only'])
async def ssl(unit, request):
    """
    Enable SSL before a test, then disable after test

    :param Agent unit:              unit from the fixture
    :param request:                 test parameters
    """
    async with config(unit, 'ssl', request.param, 'off') as value:
        yield value


@pytest.fixture
async def extra_config(unit):
    """
    Enable extraconfig for a test, and revert afterwards

    :param Agent unit:              unit from the fixture
    """
    new_conf = """
    define host{
      use                     generic-host  ; Name of host template to use
      host_name               extra_config
      alias                   extra_config Host 02
      address                 127.0.0.1
    }"""
    async with config(unit, "extraconfig", new_conf, ""):
        yield


@pytest.fixture
async def livestatus_path(unit):
    """
    Enable livestatus before a test, then disable after test

    :param Agent unit:              unit from the fixture
    """
    async with config(unit, "enable_livestatus", "true", "false"):
        app_config = await unit.application.get_config()
        yield app_config['livestatus_path']['value']


@pytest.fixture()
async def enable_pagerduty(unit):
    """
    Enable enable_pagerduty before first test, then disable after last test

    :param Agent unit:              unit from the fixture
    """
    async with config(unit, "enable_pagerduty", "true", "false"):
        app_config = await unit.application.get_config()
        yield app_config['pagerduty_path']['value']


#########
# TESTS #
#########
async def test_web_interface_with_ssl(auth, unit, ssl):
    http_url = "http://%s/nagios3/" % unit.u.public_address
    if ssl == 'only':
        with pytest.raises(requests.ConnectionError):
            requests.get(http_url, auth=auth)
    else:
        r = requests.get(http_url, auth=auth)
        assert r.status_code == 200, "HTTP Admin login failed"

    https_url = "https://%s/nagios3/" % unit.u.public_address
    r = requests.get(https_url, auth=auth, verify=False)
    assert r.status_code == 200, "HTTPs Admin login failed"


@pytest.mark.usefixtures('extra_config')
async def test_extra_config(auth, unit):
    host_url = "http://%s/cgi-bin/nagios3/status.cgi?" \
              "hostgroup=all&style=hostdetail" % unit.u.public_address
    r = requests.get(host_url, auth=auth)
    assert r.text.find('extra_config'), "Nagios is not monitoring extra_config"


async def test_live_status(unit, livestatus_path, file_stat):
    stat = await file_stat(livestatus_path, unit.u)
    assert stat['size'] == 0, (
        "File %s didn't match expected size" % livestatus_path
    )


async def test_pager_duty(unit, enable_pagerduty, file_stat):
    stat = await file_stat(enable_pagerduty, unit.u)
    assert stat['size'] != 0, (
        "Directory %s wasn't a non-zero size" % enable_pagerduty
    )
    stat = await file_stat('/etc/nagios3/conf.d/pagerduty_nagios.cfg', unit.u)
    assert stat['size'] != 0, "pagerduty_config wasn't a non-zero sized file"
