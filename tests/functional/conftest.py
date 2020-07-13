#!/usr/bin/python3

import asyncio
import json
import os
import uuid

import juju
from juju.controller import Controller
from juju.errors import JujuError
from juju.model import Model

import pytest


STAT_FILE = "python3 -c \"import json; import os; s=os.stat('%s'); print(json.dumps({'uid': s.st_uid, 'gid': s.st_gid, 'mode': oct(s.st_mode), 'size': s.st_size}))\""  # noqa: E501


@pytest.yield_fixture(scope='module')
def event_loop(request):
    """Override the default pytest event loop to allow for broaded scopedv fixtures."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    asyncio.set_event_loop(loop)
    loop.set_debug(True)
    yield loop
    loop.close()
    asyncio.set_event_loop(None)


@pytest.fixture(scope='module')
async def controller():
    """Connect to the current controller."""
    controller = Controller()
    await controller.connect_current()
    yield controller
    await controller.disconnect()


@pytest.fixture(scope='module')
async def model(controller):
    """Create a model that lives only for the duration of the test."""
    model_name = "functest-{}".format(uuid.uuid4())
    model = await controller.add_model(model_name)
    yield model
    await model.disconnect()
    if os.getenv('test_preserve_model'):
        return
    await controller.destroy_model(model_name)
    while model_name in await controller.list_models():
        await asyncio.sleep(1)


@pytest.fixture(scope='module')
async def current_model():
    """Return the current model, does not create or destroy it."""
    model = Model()
    await model.connect_current()
    yield model
    await model.disconnect()


@pytest.fixture
async def get_app(model):
    """Return the application requested."""
    async def _get_app(name):
        try:
            return model.applications[name]
        except KeyError:
            raise JujuError("Cannot find application {}".format(name))
    return _get_app


@pytest.fixture
async def get_unit(model):
    """Return the requested <app_name>/<unit_number> unit."""
    async def _get_unit(name):
        try:
            (app_name, unit_number) = name.split('/')
            return model.applications[app_name].units[unit_number]
        except (KeyError, ValueError):
            raise JujuError("Cannot find unit {}".format(name))
    return _get_unit


@pytest.fixture
async def get_entity(model, get_unit, get_app):
    """Return a unit or an application."""
    async def _get_entity(name):
        try:
            return await get_unit(name)
        except JujuError:
            try:
                return await get_app(name)
            except JujuError:
                raise JujuError("Cannot find entity {}".format(name))
    return _get_entity


@pytest.fixture
async def run_command(get_unit):
    """
    Run a command on a unit.

    :param cmd: Command to be run
    :param target: Unit object or unit name string
    """
    async def _run_command(cmd, target):
        unit = (
            target
            if type(target) is juju.unit.Unit
            else await get_unit(target)
        )
        action = await unit.run(cmd)
        return action.results
    return _run_command


@pytest.fixture
async def file_stat(run_command):
    """
    Run stat on a file.

    :param path: File path
    :param target: Unit object or unit name string
    """
    async def _file_stat(path, target):
        cmd = STAT_FILE % path
        results = await run_command(cmd, target)
        return json.loads(results['Stdout'])
    return _file_stat


@pytest.fixture
async def file_contents(run_command):
    """
    Return the contents of a file.

    :param path: File path
    :param target: Unit object or unit name string
    """
    async def _file_contents(path, target):
        cmd = 'cat {}'.format(path)
        results = await run_command(cmd, target)
        return results['Stdout']
    return _file_contents


@pytest.fixture
async def reconfigure_app(get_app, model):
    """Apply a different config to the requested app."""
    async def _reconfigure_app(cfg, target):
        application = (
            target
            if type(target) is juju.application.Application
            else await get_app(target)
        )
        await application.set_config(cfg)
        await application.get_config()
        await model.block_until(lambda: application.status == 'active')
    return _reconfigure_app


@pytest.fixture
async def create_group(run_command):
    """Create the UNIX group specified."""
    async def _create_group(group_name, target):
        cmd = "sudo groupadd %s" % group_name
        await run_command(cmd, target)
    return _create_group