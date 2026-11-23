BATTERY_THRESHOLDS = {
    "EP1": 2500,
    "EP2": 2500,
    "Canary_A": 3600,
}

API_HOSTS = {
    "AHN2": "buildroot_api.azure",
    "Cassia": "buildroot_api.azure",
    "Moxa": "moxa_api.azure",
}

VALID_NODE_TYPES = {"ahn2": "AHN2", "cassia": "Cassia", "moxa": "Moxa"}
VALID_EP_TYPES = {"ep1": "EP1", "ep2": "EP2", "canary_a": "Canary_A"}


class Endpoint:
    """Represents a sensor connected to a Node."""

    def __init__(self, serial_number, hardware_type, node_uuid, version="1", battery=3000, backlog=0):
        normalized_type = VALID_EP_TYPES.get(hardware_type.lower())
        if not normalized_type:
            raise ValueError(f"Unsupported Endpoint type: {hardware_type}")

        self.serial_number = serial_number
        self.hardware_type = normalized_type
        self.node_uuid = node_uuid
        self.version = str(version)
        self.battery = battery
        self.backlog = max(0, backlog)
        self.last_dfu_status = "IDLE"

    def get_battery_threshold(self):
        return BATTERY_THRESHOLDS[self.hardware_type]

    def drain_backlog(self, amount=None):
        """Simulates uploading pending samples. Drains all if amount is None."""
        if amount is None or amount >= self.backlog:
            self.backlog = 0
        else:
            self.backlog -= max(0, amount)
        return self.backlog

    def attempt_dfu(self, target_version):
        """Updates EndPoint firmware only if backlog is 0 and battery meets threshold."""
        if self.backlog > 0:
            self.last_dfu_status = f"DEFERRED: Pending backlog ({self.backlog} samples)"
            return False

        threshold = self.get_battery_threshold()
        if self.battery < threshold:
            self.last_dfu_status = f"DEFERRED: Low battery ({self.battery}mA < {threshold}mA)"
            return False

        self.version = str(target_version)
        self.last_dfu_status = f"UPDATED to {self.version}"
        return True

    def to_dict(self):
        return {
            "serial_number": self.serial_number,
            "battery": self.battery,
            "hardware_type": self.hardware_type,
            "uuid": self.node_uuid,
            "version": self.version,
            "backlog": self.backlog,
            "last_dfu_status": self.last_dfu_status,
        }


class Node:
    """Gateway that manages Endpoints and polls for OTA updates."""

    DEFAULT_REQUIRED_POLLS = 3

    def __init__(self, uuid, version="33", required_polls=DEFAULT_REQUIRED_POLLS):
        if "_" not in uuid:
            raise ValueError(f"Invalid Node UUID '{uuid}'. Expected <hardware_type>_<string>")

        #taking only the first part of the artifact and putting lower case
        raw_type = uuid.split("_", 1)[0].lower() 
        normalized_type = VALID_NODE_TYPES.get(raw_type)
        if not normalized_type:
            raise ValueError(f"Unsupported Node hardware type in UUID: {uuid}")

        self.uuid = uuid
        self.hardware_type = normalized_type
        self.api_host = API_HOSTS[normalized_type]
        self.ota_channel = f"OTA_{uuid}"
        self.version = str(version)
        self.endpoints = []
        self.last_error = ""

        # Internal OTA polling state
        self.required_polls = required_polls
        self._current_artifact = None
        self._poll_count = 0

    def attach_endpoint(self, serial_number):
        if serial_number not in self.endpoints:
            self.endpoints.append(serial_number)

    @staticmethod
    def parse_artifact(artifact_name):
        """Extracts (hardware_type, version) from '<hardware_type>_<version>.swu'."""
        #wrong format checking for the artifact
        if not artifact_name.endswith(".swu") or "_" not in artifact_name:
            raise ValueError(f"Invalid artifact format: {artifact_name}")

        base_name = artifact_name[:-4]
        hw_part, version_part = base_name.split("_", 1)
        if not hw_part or not version_part:
            raise ValueError(f"Malformed artifact name: {artifact_name}")
        return hw_part, version_part

    def poll_ota(self, channel_artifacts):
        """Simulates a single OTA poll cycle. Returns True when version updates."""
        if not channel_artifacts:
            self._current_artifact = None
            self._poll_count = 0
            return False
        #taking the latest artifact available, we dont want the old ones
        artifact = channel_artifacts[-1]

        try:
            artifact_hw, target_version = self.parse_artifact(artifact)
        except ValueError as err:
            self.last_error = str(err)
            self._current_artifact = None
            self._poll_count = 0
            return False

        # Case-insensitive hardware validation
        if artifact_hw.lower() != self.hardware_type.lower():
            self.last_error = (
                f"Hardware mismatch: Node is '{self.hardware_type}', "
                f"received '{artifact_hw}' ({artifact})"
            )
            self._current_artifact = None
            self._poll_count = 0
            return False

        # Valid artifact - advance poll counter
        self.last_error = ""
        if self._current_artifact != artifact:
            self._current_artifact = artifact
            self._poll_count = 1
        else:
            self._poll_count += 1

        if self._poll_count >= self.required_polls:
            self.version = target_version
            self._current_artifact = None
            self._poll_count = 0
            return True

        return False

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "hardware_type": self.hardware_type,
            "api_host": self.api_host,
            "ota_channel": self.ota_channel,
            "version": self.version,
            "endpoints": list(self.endpoints),
            "last_error": self.last_error,
        }


class IoTSystem:
    """In-memory state holder for Nodes, Endpoints, and OTA channels."""

    def __init__(self):
        self.nodes = {}
        self.endpoints = {}
        self.ota_channels = {}

    def reset(self):
        self.nodes.clear()
        self.endpoints.clear()
        self.ota_channels.clear()