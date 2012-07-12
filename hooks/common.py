import subprocess
import socket
import os
import os.path
import re

from pynag import Model

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
    hostgroup_path = hostgroup_path_template % (relation_id)
    if os.path.exists(hostgroup_path):
        os.unlink(hostgroup_path)


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
        with open(hostgroup_path, 'w') as outfile:
            outfile.write(hostgroup_template % {'name': service,
                'alias': service, 'members': ','.join(members)})

def refresh_hostgroups(relation_name):
    p = subprocess.Popen(["relation-ids",relation_name],
        stdout=subprocess.PIPE)
    relids = [ relation_id.strip() for relation_id in p.stdout ]
    for relation_id in relids:
        remove_hostgroup(relation_id)
        handle_hostgroup(relation_id)
    p.communicate()
    if p.returncode != 0:
        raise RuntimeError('relation-ids failed with code %d' % p.returncode)


def get_default_tag_value():
    return os.environ.get('JUJU_RELATION_ID', 'testing')


def get_tag_file(value):
    if value is None:
        value = get_default_tag_value()
    if not os.path.exists('data'):
        os.mkdir('data')
    return 'data/%s' % value


def tag_object(obj, value=None):
    if value is None:
        value = get_default_tag_value()
    with open(get_tag_file(value),'a+') as tagdata:
        files = set([x.strip() for x in tagdata.readlines()])
        fname = obj.get_suggested_filename()
        if fname not in files:
            tagdata.write("%s\n" % fname)


def get_all_monitors_tags():
    result = {}
    relids = subprocess.Popen(['relation-ids', 'monitors'], stdout=subprocess.PIPE)
    all_relids = set([relid.strip() for relid in relids.stdout])
    relids.wait()
    # During broken, reliation-ids will not show "my" relid
    my_relid = get_default_tag_value()
    all_relids.add(my_relid)
    for relid in all_relids:
        rel_file = get_tag_file(relid)
        if os.path.exists(rel_file):
            with open(rel_file, 'r') as tagdata:
                files = [l.strip() for l in tagdata]
                for f in files:
                    if f in result:
                        result[f].add(relid)
                    else:
                        result[f]=set()
                        result[f].add(relid)
    return result
            

def remove_tagged_objects(value=None):
    if value is None:
        value = get_default_tag_value()
    all_tags = get_all_monitors_tags()
    rel_file = get_tag_file(value)
    if os.path.exists(rel_file):
        with open(rel_file, 'r') as tagdata:
            for f in [l.strip() for l in tagdata]:
                if f in all_tags:
                    all_tags[f].remove(value) 
                    if len(all_tags[f]) == 0:
                        try:
                            subprocess.call(['juju-log','removing %s' % (f)])
                            os.unlink(f)
                        except IOError, e:
                            subprocess.call(['juju-log','failed to remove %s (%s)' % (f,e)])
        os.unlink(rel_file)


def make_check_command(args):
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


def customize_service(service, family, extra):
    if family == 'http':
        args = []
        cmd_args = []
        plugin = os.path.join(PLUGIN_PATH, 'check_http')
        port = extra.get('port', 80)
        path = extra.get('path', '/')
        args = [port, path]
        cmd_args = [plugin, '-p', '"$ARG1$"', '-u', '"$ARG2$"']
        if 'status' in extra:
            args.append(extra['status'])
            cmd_args.extend(('-e', '"$ARG%d$"' % len(args)))
        if 'host' in extra:
            args.append(extra['host'])
            cmd_args.extend(('-H', '"$ARG%d$"' % len(args)))
            cmd_args.extend(('-I', '$HOSTADDRESS$'))
        else:
            cmd_args.extend(('-H', '$HOSTADDRESS$'))
        check_command = make_check_command(cmd_args)
        cmd = '%s!%s' % (check_command, '!'.join([str(x) for x in args]))
        service.set_attribute('check_command', cmd)
        return True
    return False
