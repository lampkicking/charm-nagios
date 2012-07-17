import subprocess
import socket
import os
import os.path
import re
import sqlite3

from pynag import Model

Model.cfg_file = '/etc/nagios3/nagios.cfg'
Model.pynag_directory = '/etc/nagios3/conf.d'

reduce_RE = re.compile('[\W_]')
PLUGIN_PATH = '/usr/lib/nagios/plugins'

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


def get_ip_and_hostname(remote_unit, relation_id=None):
    args=["relation-get", "private-address", remote_unit]
    if relation_id is not None:
        args.extend(['-r', relation_id])
    hostname = subprocess.check_output(args).strip()
        
    if hostname is None or not len(hostname):
        print "relation-get failed"
        return 2
    if check_ip(hostname):
        # Some providers don't provide hostnames, so use the remote unit name.
        ip_address = hostname
        hostname = remote_unit.replace('/','-')
    else:
        ip_address = socket.getaddrinfo(hostname, None)[0][4][0]
    return (ip_address, hostname)

# relationId-hostname-config.cfg
host_config_path_template = '/etc/nagios3/conf.d/%s-%s-config.cfg'

hostgroup_template = """
define hostgroup {
    hostgroup_name  %(name)s
    alias   %(alias)s
    members %(members)s
}
"""
hostgroup_path_template = '/etc/nagios3/conf.d/%s-hostgroup.cfg'


def remove_hostgroup(relation_id):
    hgroup_relations.kill_tag(relation_id)
    hgroup_relations.cleanup_untagged()


def handle_hostgroup(relation_id):
    p = subprocess.Popen(["relation-list","-r",relation_id],
                         stdout=subprocess.PIPE)
    services = {}
    for unit in p.stdout:
        unit = unit.strip()
        service_name = unit.strip().split('/')[0]
        (_, hostname) = get_ip_and_hostname(unit, relation_id)
        if service_name in services:
            services[service_name].add(hostname)
        else:
            services[service_name] = set([hostname])
    p.communicate()
    if p.returncode != 0:
        raise RuntimeError('relation-list failed with code %d' % p.returncode)

    hostgroup_path = hostgroup_path_template % (relation_id)
    for service, members in services.iteritems():
        try:
            hgroup = Model.Hostgroup.objects.get_by_shortname(service)
        except ValueError:
            hgroup = Model.Hostgroup()
            hgroup.set_attribute('hostgroup_name', service)

        hgroup.set_attribute('members', ','.join(members))
        hgroup.save()
        hgroup_relations.tag_object(hgroup, relation_id)

def refresh_hostgroup_by_relid(relation_id):
    remove_hostgroup(relation_id)
    handle_hostgroup(relation_id)


def refresh_hostgroups(relation_name):
    p = subprocess.Popen(["relation-ids",relation_name],
        stdout=subprocess.PIPE)
    relids = [ relation_id.strip() for relation_id in p.stdout ]
    for relation_id in relids:
        refresh_hostgroup_by_relid(relation_id)
    p.communicate()
    if p.returncode != 0:
        raise RuntimeError('relation-ids failed with code %d' % p.returncode)


class ObjectTagCollection(object):

    path = os.path.join('data','tags.db')

    def __init__(self, tagtype):
        self.tagtype = tagtype
        ddir = os.path.dirname(type(self).path)
        if not os.path.exists(ddir):
            os.mkdir(ddir)
        self._sqlite = sqlite3.Connection(type(self).path)
        self._sqlite.execute('CREATE TABLE IF NOT EXISTS obj (obj text PRIMARY KEY)')
        self._sqlite.execute('CREATE TABLE IF NOT EXISTS `%s` (obj text, tag text, PRIMARY KEY( obj, tag ))' % (tagtype))

    def destroy(self):
        self._sqlite = None
        os.unlink(type(self).path)

    def tag_object(self, obj, value):
        self._sqlite.execute('INSERT OR IGNORE INTO obj VALUES(?)', (obj,))
        self._sqlite.execute("INSERT OR IGNORE INTO `%s` VALUES (?,?)" % (self.tagtype), (obj, value))
        self._sqlite.commit()

    def untag_object(self, obj, value):
        self._sqlite.execute('DELETE FROM `%s` WHERE obj = ? AND tag = ?' % (self.tagtype), (obj, value))
        self._sqlite.commit()

    def kill_tag(self, value):
        self._sqlite.execute('DELETE FROM `%s` WHERE tag = ?' % (self.tagtype), (value,))
        self._sqlite.commit()

    def cleanup_untagged(self, valid_tags=[]):
        if len(valid_tags):
            self._sqlite.execute(
                "DELETE FROM `%s` WHERE tag NOT IN (%s)" % (self.tagtype, ','.join('?'*len(valid_tags))),
                valid_tags)

        sql = """
            SELECT o.obj
            FROM obj AS o LEFT OUTER JOIN `%s` AS t ON o.obj = t.obj
            WHERE t.obj IS NULL""" % self.tagtype

        results = self._sqlite.execute(sql)
        for row in results:
            if os.path.exists(row[0]):
                os.unlink(row[0])
            self._sqlite.execute("DELETE FROM obj WHERE obj = ?", (row[0],))
            self._sqlite.commit()


def _make_check_command(args):
    args = [str(arg) for arg in args]
    # There is some worry of collision, but the uniqueness of the initial
    # command should be enough.
    signature = reduce_RE.sub('_', ''.join(
                [os.path.basename(arg) for arg in args]))
    try:
        cmd = Model.Command.objects.get_by_shortname(signature)
    except ValueError:
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
    check_command = _make_check_command(cmd_args)
    cmd = '%s!%s' % (check_command, '!'.join([str(x) for x in args]))
    service.set_attribute('check_command', cmd)
    return True


def customize_mysql(service, name, extra):
    plugin = os.path.join(PLUGIN_PATH, 'check_mysql')
    args = []
    cmd_args = [plugin,'-H', '$HOSTADDRESS$']
    if 'user' in extra:
        _extend_args(args, cmd_args, '-u', extra['user'])
    if 'password' in extra:
        _extend_args(args, cmd_args, '-p', extra['password'])
    check_command = _make_check_command(cmd_args)
    cmd = '%s!%s' % (check_command, '!'.join([str(x) for x in args]))
    service.set_attribute('check_command', cmd)
    return True


def customize_nrpe(service, name, extra):
    plugin = os.path.join(PLUGIN_PATH, 'check_nrpe')
    args = []
    cmd_args = [plugin,'-H', '$HOSTADDRESS$']
    if name in ('mem','swap'):
        cmd_args.extend(('-c', 'check_%s' % name))
    elif 'command' in extra:
        cmd_args.extend(('-c', extra['command']))
    else:
        return False
    check_command = _make_check_command(cmd_args)
    cmd = '%s!%s' % (check_command, '!'.join([str(x) for x in args]))
    service.set_attribute('check_command', cmd)
    return True


def customize_service(service, family, name, extra):
    customs = { 'http': customize_http,
                'mysql': customize_mysql,
                'nrpe': customize_nrpe}
    if family in customs:
        return customs[family](service, name, extra)
    return False


def get_pynag_host(target_id):
    try:
        host = Model.Host.objects.get_by_shortname(target_id)
    except ValueError:
        host = Model.Host()
        host.set_attribute('host_name', target_id)
        host.set_attribute('use', 'generic-host')
        host.save()
        # The newly created object is now somehow tained, pynag weirdness.
        host = Model.Host.objects.get_by_shortname(target_id)
    apply_host_policy(target_id)
    return host


def get_pynag_service(target_id, service_name):
    services = Model.Service.objects.filter(host_name=target_id,
                    service_description=service_name)
    if len(services) == 0:
        service = Model.Service()
        service.set_attribute('service_description', service_name)
        service.set_attribute('host_name', target_id)
        service.set_attribute('use', 'generic-service')
    else:
        service = services[0]
    return service


def apply_host_policy(target_id):
    ssh_service = get_pynag_service(target_id, 'SSH')
    ssh_service.set_attribute('check_command', 'check_ssh')
    ssh_service.save()


units = ObjectTagCollection('units')
relations = ObjectTagCollection('relations')
hgroup_relations = ObjectTagCollection('hgroup_relations')
