#!/bin/sh

POSTFIX_CONF="/etc/postfix/main.cf"
if grep -qE '^inet_interfaces.*all' $POSTFIX_CONF; then
    sed -i 's/^inet_interfaces.*/inet_interfaces = loopback-only/' $POSTFIX_CONF
    systemctl restart postfix
fi
