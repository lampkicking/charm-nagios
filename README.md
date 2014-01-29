# Overview

[Nagios](http://nagios.org) offers complete monitoring and alerting for servers, switches, applications, and services.

This charm is designed to do basic monitoring of any service in the Charm Store that relates to it. There is an [NRPE subordinate charm](https://jujucharms.com/precise/nrpe/) that you can use if you want to use local monitors. 

# Usage

This charm is designed to be used with other charms. In order to monitor anything in your juju environment for working PING and SSH, just relate the services to this service. In this example we deploy a central monitoring instance, mediawiki, a database, and then monitor them with Nagios:

    juju deploy nagios central-monitor
    juju deploy mysql big-db
    juju deploy mediawiki big-wiki
    juju add-reation big-db big-wiki
    juju add-relation big-db central-monitor
    juju add-relation big-wiki central-monitor

This should result in your Nagios monitoring all of the service units.

There is an [NRPE subordinate charm](https://jujucharms.com/precise/nrpe/) which must be used for any local monitors.  See the `nrpe` charm's README for information on how to make use of it.

You can expose the service and browse to `http://x.x.x.x/nagios3` to get to the web UI, following the example:

    juju expose central-monitor
    juju status central-monitor

Will get you the public IP of the web interface.

## Known Limitations and Issues

# Configuration

The monitors interface expects three fields:

- `monitors` - YAML matching the monitors yaml spec. See example.monitors.yaml for more information.
- `target-id` - Assign any monitors to this target host definition.
- `target-address` - Optional, specifies the host of the target to monitor. This must be specified by at least one unit so that the intended target-id will be monitorable.

# Contact Information

## Nagios

- [Nagios homepage](http://nagios.org)
- [Nagios documentation](http://www.nagios.org/documentation)
- [Nagios support](http://www.nagios.org/support)
