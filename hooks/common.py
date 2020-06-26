import subprocess
import socket
import os
import os.path
import re
import shutil
import tempfile

from charmhelpers.core.hookenv import (
    log,
    network_get,
    network_get_primary_address,
    unit_get,
    config,
)

from pynag import Model

INPROGRESS_DIR = '/etc/nagios3-inprogress'
INPROGRESS_CFG = '/etc/nagios3-inprogress/nagios.cfg'
INPROGRESS_CONF_D = '/etc/nagios3-inprogress/conf.d'
CHARM_CFG = '/etc/nagios3-inprogress/conf.d/charm.cfg'
MAIN_NAGIOS_BAK = '/etc/nagios3.bak'
MAIN_NAGIOS_DIR = '/etc/nagios3'
MAIN_NAGIOS_CFG = '/etc/nagios3/nagios.cfg'
PLUGIN_PATH = '/usr/lib/nagios/plugins'

Model.cfg_file = INPROGRESS_CFG
Model.pynag_directory = INPROGRESS_CONF_D

reduce_RE = re.compile(r'[\W_]')


def check_ip(n):
    try:
        socket.inet_pton(socket.AF_INET, n)
        return True
    except socket.error:
        try:
            socket.inet_pton(socket.AF_INET6, n)
            return True
        except socket.error:
            return False


def get_local_ingress_address(binding='website'):
    # using network-get to retrieve the address details if available.
    log('Getting hostname for binding %s' % binding)
    try:
        network_info = network_get(binding)
        if network_info is not None and 'ingress-addresses' in network_info:
            log('Using ingress-addresses')
            hostname = network_info['ingress-addresses'][0]
            log(hostname)
            return hostname
    except NotImplementedError:
        # We'll fallthrough to the Pre 2.3 code below.
        pass

    # Pre 2.3 output
    try:
        hostname = network_get_primary_address(binding)
        log('Using primary-addresses')
    except NotImplementedError:
        # pre Juju 2.0
        hostname = unit_get('private-address')
        log('Using unit_get private address')
    log(hostname)
    return hostname


def get_remote_relation_attr(remote_unit, attr_name, relation_id=None):
    args = ["relation-get", attr_name, remote_unit]
    if relation_id is not None:
        args.extend(['-r', relation_id])
    return subprocess.check_output(args).strip()


def get_ip_and_hostname(remote_unit, relation_id=None):
    hostname = get_remote_relation_attr(remote_unit, 'ingress-address', relation_id)
    if hostname is None or not len(hostname):
        hostname = get_remote_relation_attr(remote_unit, 'private-address', relation_id)

    if hostname is None or not len(hostname):
        log("relation-get failed")
        return 2
    if check_ip(hostname):
        # Some providers don't provide hostnames, so use the remote unit name.
        ip_address = hostname
    else:
        ip_address = socket.getaddrinfo(hostname, None)[0][4][0]
    return (ip_address, remote_unit.replace('/', '-'))


def refresh_hostgroups():
    """ Not the most efficient thing but since we're only
        parsing what is already on disk here its not too bad """
    hosts = [x['host_name'] for x in Model.Host.objects.all if x['host_name']]

    hgroups = {}
    for host in hosts:
        try:
            (service, unit_id) = host.rsplit('-', 1)
        except ValueError:
            continue
        if service in hgroups:
            hgroups[service].append(host)
        else:
            hgroups[service] = [host]

    # Find existing autogenerated
    auto_hgroups = Model.Hostgroup.objects.filter(notes__contains='#autogenerated#')
    auto_hgroups = [x.get_attribute('hostgroup_name') for x in auto_hgroups]

    # Delete the ones not in hgroups
    to_delete = set(auto_hgroups).difference(set(hgroups.keys()))
    for hgroup_name in to_delete:
        try:
            hgroup = Model.Hostgroup.objects.get_by_shortname(hgroup_name)
            hgroup.delete()
        except (ValueError, KeyError):
            pass

    for hgroup_name, members in hgroups.iteritems():
        try:
            hgroup = Model.Hostgroup.objects.get_by_shortname(hgroup_name)
        except (ValueError, KeyError):
            hgroup = Model.Hostgroup()
            hgroup.set_filename(CHARM_CFG)
            hgroup.set_attribute('hostgroup_name', hgroup_name)
            hgroup.set_attribute('notes', '#autogenerated#')

        hgroup.set_attribute('members', ','.join(members))
        hgroup.save()


def _make_check_command(args):
    args = [str(arg) for arg in args]
    # There is some worry of collision, but the uniqueness of the initial
    # command should be enough.
    signature = reduce_RE.sub('_', ''.join(
                [os.path.basename(arg) for arg in args]))
    Model.Command.objects.reload_cache()
    try:
        cmd = Model.Command.objects.get_by_shortname(signature)
    except (ValueError, KeyError):
        cmd = Model.Command()
        cmd.set_attribute('command_name', signature)
        cmd.set_attribute('command_line', ' '.join(args))
        cmd.save()
    return signature


def _extend_args(args, cmd_args, switch, value):
    args.append(value)
    cmd_args.extend((switch, '"$ARG%d$"' % len(args)))


def customize_http(service, name, extra):
    args = []
    cmd_args = []
    plugin = os.path.join(PLUGIN_PATH, 'check_http')
    port = extra.get('port', 80)
    path = extra.get('path', '/')
    args = [port, path]
    cmd_args = [plugin, '-p', '"$ARG1$"', '-u', '"$ARG2$"']
    if 'status' in extra:
        _extend_args(args, cmd_args, '-e', extra['status'])
    if 'host' in extra:
        _extend_args(args, cmd_args, '-H', extra['host'])
        cmd_args.extend(('-I', '$HOSTADDRESS$'))
    else:
        cmd_args.extend(('-H', '$HOSTADDRESS$'))
    check_timeout = config('check_timeout')
    if check_timeout is not None:
        cmd_args.extend(('-t', check_timeout))
    check_command = _make_check_command(cmd_args)
    cmd = '%s!%s' % (check_command, '!'.join([str(x) for x in args]))
    service.set_attribute('check_command', cmd)
    return True


def customize_mysql(service, name, extra):
    plugin = os.path.join(PLUGIN_PATH, 'check_mysql')
    args = []
    cmd_args = [plugin, '-H', '$HOSTADDRESS$']
    if 'user' in extra:
        _extend_args(args, cmd_args, '-u', extra['user'])
    if 'password' in extra:
        _extend_args(args, cmd_args, '-p', extra['password'])
    check_timeout = config('check_timeout')
    if check_timeout is not None:
        cmd_args.extend(('-t', check_timeout))
    check_command = _make_check_command(cmd_args)
    cmd = '%s!%s' % (check_command, '!'.join([str(x) for x in args]))
    service.set_attribute('check_command', cmd)
    return True


def customize_pgsql(service, name, extra):
    plugin = os.path.join(PLUGIN_PATH, 'check_pgsql')
    args = []
    cmd_args = [plugin, '-H', '$HOSTADDRESS$']
    check_timeout = config('check_timeout')
    if check_timeout is not None:
        cmd_args.extend(('-t', check_timeout))
    check_command = _make_check_command(cmd_args)
    cmd = '%s!%s' % (check_command, '!'.join([str(x) for x in args]))
    service.set_attribute('check_command', cmd)
    return True


def customize_nrpe(service, name, extra):
    plugin = os.path.join(PLUGIN_PATH, 'check_nrpe')
    args = []
    cmd_args = [plugin, '-H', '$HOSTADDRESS$']
    if name in ('mem', 'swap'):
        cmd_args.extend(('-c', 'check_%s' % name))
    elif 'command' in extra:
        cmd_args.extend(('-c', extra['command']))
    else:
        cmd_args.extend(('-c', extra))
    check_timeout = config('check_timeout')
    if check_timeout is not None:
        cmd_args.extend(('-t', check_timeout))
    check_command = _make_check_command(cmd_args)
    cmd = '%s!%s' % (check_command, '!'.join([str(x) for x in args]))
    service.set_attribute('check_command', cmd)
    return True


def customize_rpc(service, name, extra):
    """ Customize the check_rpc plugin to check things like nfs."""
    plugin = os.path.join(PLUGIN_PATH, 'check_rpc')
    args = []
    # /usr/lib/nagios/plugins/check_rpc -H <host> -C <rpc_command>
    cmd_args = [plugin, '-H', '$HOSTADDRESS$']
    if 'rpc_command' in extra:
        cmd_args.extend(('-C', extra['rpc_command']))
    if 'program_version' in extra:
        cmd_args.extend(('-c', extra['program_version']))

    check_command = _make_check_command(cmd_args)
    cmd = '%s!%s' % (check_command, '!'.join([str(x) for x in args]))
    service.set_attribute('check_command', cmd)
    return True


def customize_tcp(service, name, extra):
    """ Customize tcp can be used to check things like memcached. """
    plugin = os.path.join(PLUGIN_PATH, 'check_tcp')
    args = []
    # /usr/lib/nagios/plugins/check_tcp -H <host> -E
    cmd_args = [plugin, '-H', '$HOSTADDRESS$', '-E']
    if 'port' in extra:
        cmd_args.extend(('-p', extra['port']))
    if 'string' in extra:
        cmd_args.extend(('-s', "'{}'".format(extra['string'])))
    if 'expect' in extra:
        cmd_args.extend(('-e', extra['expect']))
    if 'warning' in extra:
        cmd_args.extend(('-w', extra['warning']))
    if 'critical' in extra:
        cmd_args.extend(('-c', extra['critical']))
    if 'timeout' in extra:
        cmd_args.extend(('-t', extra['timeout']))
    check_timeout = config('check_timeout')
    if check_timeout is not None:
        cmd_args.extend(('-t', check_timeout))

    check_command = _make_check_command(cmd_args)
    cmd = '%s!%s' % (check_command, '!'.join([str(x) for x in args]))
    service.set_attribute('check_command', cmd)
    return True


def customize_service(service, family, name, extra):
    """ The monitors.yaml names are mapped to methods that customize services. """
    customs = {'http': customize_http,
               'mysql': customize_mysql,
               'nrpe': customize_nrpe,
               'tcp': customize_tcp,
               'rpc': customize_rpc,
               'pgsql': customize_pgsql,
               }
    if family in customs:
        return customs[family](service, name, extra)
    return False


def update_localhost():
    """ Update the localhost definition to use the ubuntu icons."""

    Model.cfg_file = MAIN_NAGIOS_CFG
    Model.pynag_directory = os.path.join(MAIN_NAGIOS_DIR, 'conf.d')
    hosts = Model.Host.objects.filter(host_name='localhost',
                                      object_type='host')
    for host in hosts:
        host.icon_image = 'base/ubuntu.png'
        host.icon_image_alt = 'Ubuntu Linux'
        host.vrml_image = 'ubuntu.png'
        host.statusmap_image = 'base/ubuntu.gd2'
        host.save()


def get_pynag_host(target_id, owner_unit=None, owner_relation=None):
    try:
        host = Model.Host.objects.get_by_shortname(target_id)
    except (ValueError, KeyError):
        host = Model.Host()
        host.set_filename(CHARM_CFG)
        host.set_attribute('host_name', target_id)
        host.set_attribute('use', 'generic-host')
        # Adding the ubuntu icon image definitions to the host.
        host.set_attribute('icon_image', 'base/ubuntu.png')
        host.set_attribute('icon_image_alt', 'Ubuntu Linux')
        host.set_attribute('vrml_image', 'ubuntu.png')
        host.set_attribute('statusmap_image', 'base/ubuntu.gd2')
        host.save()
        host = Model.Host.objects.get_by_shortname(target_id)
    apply_host_policy(target_id, owner_unit, owner_relation)
    return host


def get_pynag_service(target_id, service_name):
    services = Model.Service.objects.filter(host_name=target_id,
                                            service_description=service_name)
    if len(services) == 0:
        service = Model.Service()
        service.set_filename(CHARM_CFG)
        service.set_attribute('service_description', service_name)
        service.set_attribute('host_name', target_id)
        service.set_attribute('use', 'generic-service')
    else:
        service = services[0]
    return service


def apply_host_policy(target_id, owner_unit, owner_relation):
    ssh_service = get_pynag_service(target_id, 'SSH')
    ssh_service.set_attribute('check_command', 'check_ssh')
    ssh_service.save()


def get_valid_relations():
    for x in subprocess.Popen(['relation-ids', 'monitors'],
                              stdout=subprocess.PIPE).stdout:
        yield x.strip()
    for x in subprocess.Popen(['relation-ids', 'nagios'],
                              stdout=subprocess.PIPE).stdout:
        yield x.strip()


def get_valid_units(relation_id):
    for x in subprocess.Popen(['relation-list', '-r', relation_id],
                              stdout=subprocess.PIPE).stdout:
        yield x.strip()


def _replace_in_config(find_me, replacement):
    with open(INPROGRESS_CFG) as cf:
        with tempfile.NamedTemporaryFile(dir=INPROGRESS_DIR, delete=False) as new_cf:
            for line in cf:
                new_cf.write(line.replace(find_me, replacement))
            new_cf.flush()
            os.chmod(new_cf.name, 0o644)
            os.unlink(INPROGRESS_CFG)
            os.rename(new_cf.name, INPROGRESS_CFG)


def _commit_in_config(find_me, replacement):
    with open(MAIN_NAGIOS_CFG) as cf:
        with tempfile.NamedTemporaryFile(dir=MAIN_NAGIOS_DIR, delete=False) as new_cf:
            for line in cf:
                new_cf.write(line.replace(find_me, replacement))
            new_cf.flush()
            os.chmod(new_cf.name, 0o644)
            os.unlink(MAIN_NAGIOS_CFG)
            os.rename(new_cf.name, MAIN_NAGIOS_CFG)


def initialize_inprogress_config():
    if os.path.exists(INPROGRESS_DIR):
        shutil.rmtree(INPROGRESS_DIR)
    shutil.copytree(MAIN_NAGIOS_DIR, INPROGRESS_DIR)
    _replace_in_config(MAIN_NAGIOS_DIR, INPROGRESS_DIR)
    if os.path.exists(CHARM_CFG):
        os.unlink(CHARM_CFG)


def flush_inprogress_config():
    if not os.path.exists(INPROGRESS_DIR):
        return
    if os.path.exists(MAIN_NAGIOS_BAK):
        shutil.rmtree(MAIN_NAGIOS_BAK)
    if os.path.exists(MAIN_NAGIOS_DIR):
        shutil.move(MAIN_NAGIOS_DIR, MAIN_NAGIOS_BAK)
    shutil.move(INPROGRESS_DIR, MAIN_NAGIOS_DIR)
    # now that directory has been changed need to update the config file to reflect the real stuff..
    _commit_in_config(INPROGRESS_DIR, MAIN_NAGIOS_DIR)
