# Network verification

Network verification is planned as one input to attendance policy, not as proof of identity by itself. The mobile contracts can eventually report a Wi-Fi SSID/BSSID when the operating system and permissions permit it, plus location coordinates, accuracy, and capture time.

GPS can be imprecise or unavailable indoors and should be evaluated with accuracy and freshness limits. Wi-Fi identifiers are restricted by platform permissions and privacy rules; availability differs across Android and iOS releases. A reported network or coordinate can be spoofed and must not be trusted without backend policy and supporting controls.

No GPS, BSSID, or attendance verification is implemented. Current plugin contracts return an explicit unavailable result.
