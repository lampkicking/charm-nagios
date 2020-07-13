import pytest

import requests
pytestmark = pytest.mark.asyncio


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


@pytest.fixture
async def extra_config(model, deploy_app, unit):
    """
    Enable extraconfig for a test, and revert afterwards

    :param Model model:             Current deployed model
    :param Application deploy_app:  Application under test
    :param Agent unit:              unit from the fixture
    """
    await deploy_app.set_config({
        "extraconfig": """
    define host{
      use                     generic-host  ; Name of host template to use
      host_name               extra_config
      alias                   extra_config Host 02
      address                 127.0.0.1
    }"""})
    await unit.block_until(lambda: unit.is_active('executing'))
    await unit.block_until(lambda: unit.is_active('idle'))
    yield
    await deploy_app.set_config({"extraconfig": ""})
    await unit.block_until(lambda: unit.is_active('executing'))
    await unit.block_until(lambda: unit.is_active('idle'))


@pytest.fixture
async def livestatus_path(model, deploy_app, unit):
    """
    Enable livestatus before a test, then disable after test

    :param Model model:             Current deployed model
    :param Application deploy_app:  Application under test
    :param Agent unit:              unit from the fixture
    """
    await deploy_app.set_config({"enable_livestatus": "true"})
    await unit.block_until(lambda: unit.is_active('executing'))
    await unit.block_until(lambda: unit.is_active('idle'))
    yield (await deploy_app.get_config())['livestatus_path']['value']
    await deploy_app.set_config({"enable_livestatus": "false"})
    await unit.block_until(lambda: unit.is_active('executing'))
    await unit.block_until(lambda: unit.is_active('idle'))


@pytest.fixture()
async def enable_pagerduty(model, deploy_app, unit):
    """
    Enable enable_pagerduty before first test, then disable after last test

    :param Model model:             Current deployed model
    :param Application deploy_app:  Application under test
    :param Agent unit:              unit from the fixture
    """
    await deploy_app.set_config({"enable_pagerduty": "true"})
    await unit.block_until(lambda: unit.is_active('executing'))
    await unit.block_until(lambda: unit.is_active('idle'))
    yield (await deploy_app.get_config())['pagerduty_path']['value']
    await deploy_app.set_config({"enable_pagerduty": "false"})
    await unit.block_until(lambda: unit.is_active('executing'))
    await unit.block_until(lambda: unit.is_active('idle'))


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
