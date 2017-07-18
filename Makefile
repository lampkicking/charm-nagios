default:
	echo Nothing to do

# Primitive test runner. Someone please fix this.
test:
	tests/00-setup
	tests/100-deploy
	tests/10-initial-test
	tests/15-nrpe-test
	tests/20-ssl-test
	tests/21-monitors-interface-test
	tests/22-extraconfig-test
	tests/23-livestatus-test
	tests/24-pagerduty-test
