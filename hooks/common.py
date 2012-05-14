import subprocess
import socket


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


def get_ip_and_hostname(remote_unit):
    p = subprocess.Popen(["relation-get", "private-address"],
                         stdout=subprocess.PIPE)
    hostname=p.stdout.read().strip()
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
