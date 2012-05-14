import subprocess
import socket
import os
import os.path


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
