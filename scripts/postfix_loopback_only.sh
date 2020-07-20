#!/bin/sh

POSTFIX_CONF="/etc/postfix/main.cf"
CODENAME="$(lsb_release -a | grep -E '^Codename:' | awk '{print $2}')"
if [ $CODENAME = "trusty" ] ; then CMD="/etc/init.d/postfix restart" ; else CMD="systemctl restart postfix" ; fi

if grep -qE '^inet_interfaces.*all' $POSTFIX_CONF; then
    sed -i 's/^inet_interfaces.*/inet_interfaces = loopback-only/' $POSTFIX_CONF
    $CMD
fi

