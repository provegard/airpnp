Feature: UPnP discovery and detection
	As a user
	I want AirPnp to discover UPnP devices
	So that it can expose them as AirPlay servers

	Scenario: Send SSDP M-SEARCH message
		Given an empty configuration
		And I listen for discovery messages 
		When I start Airpnp
		Then I will see the following discovery message:
			"""
			M-SEARCH * HTTP/1.1
			HOST: 239.255.255.250:1900
			MAN: "ssdp:discover""
			MX: 5
			ST: ssdp:all
			"""

