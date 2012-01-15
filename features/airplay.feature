Feature: AirPlay service publishing
	As a user
	I want AirPnp to publish an AirPlay service for each UPnP device
	So that an iDevice can detect the UPnP device

  Scenario: Publish AirPlay service
    Given an empty configuration
    And a media renderer with UDN uuid:00000000-0000-0000-0000-001122334455 and name MR1 is running
    When Airpnp is started
    Then an AirPlay service is published with the name MR1
    And the AirPlay service has features set to 0x77
    And the AirPlay service has model set to AppleTV2,1

