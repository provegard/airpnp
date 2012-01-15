Feature: Starting Airpnp
	As a user
	I want to start Airpnp
	So that it can start bridging AirPlay and UPnP devices

	Scenario: Verify aliveness
		Given an empty configuration
		When Airpnp is started
		Then the log should contain the message "Airpnp started"

