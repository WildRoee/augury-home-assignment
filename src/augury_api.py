# When running from the project root, Python imports 'src.models'.
# When Robot Framework runs from the 'tests/' folder, it imports 'models' directly.
try:
    from src.models import Endpoint, IoTSystem, Node
except ImportError:
    from models import Endpoint, IoTSystem, Node

# Single in-memory system instance shared across API calls
_system = IoTSystem()

# 1. Core API Functions

def api_get_endpoint_by_serial(serial_number):
    """Finds an Endpoint by its serial number and returns its fields as a dictionary."""
    if serial_number not in _system.endpoints:
        raise KeyError(f"Endpoint '{serial_number}' not found")
    # Convert the Endpoint object into the exact dictionary shape expected by the API
    return _system.endpoints[serial_number].to_dict()


def api_get_node_by_uuid(uuid):
    """Finds a Node by its UUID and returns its fields as a dictionary."""
    if uuid not in _system.nodes:
        raise KeyError(f"Node '{uuid}' not found")
    # Convert the Node object into the exact dictionary shape expected by the API
    return _system.nodes[uuid].to_dict()


def api_post_version_to_ota_channel(ota_channel, version_artifact):
    """
    Posts a firmware artifact filename (e.g. 'moxa_34.swu') to a Node's OTA channel.
    Returns 200 on success, 400 if channel is missing or input is empty.
    """
    if ota_channel not in _system.ota_channels or not version_artifact:
        return 400
    # Append the artifact to the channel's queue (list of pending files)
    _system.ota_channels[ota_channel].append(str(version_artifact))
    return 200


def api_clear_ota_channel(ota_channel, version_artifact):
    """
    Removes a specific firmware artifact from an OTA channel.
    Returns 200 if removed successfully, or 400 if the channel or artifact does not exist.
    """
    if ota_channel not in _system.ota_channels:
        return 400
    channel_queue = _system.ota_channels[ota_channel]
    if version_artifact not in channel_queue:
        return 400
    channel_queue.remove(version_artifact)
    return 200


# Test Setup & Simulation Helpers

def reset_system():
    """Wipes all nodes, endpoints, and channels from memory so each test starts clean."""
    _system.reset()


def init_node(uuid, version="33", required_polls=3):
    """
    Creates a new Node, registers it in the system, and opens its dedicated OTA channel.
    also because Robot Framework passes all arguments as strings, required_polls is cast to int.
    """
    node = Node(uuid=uuid, version=str(version), required_polls=int(required_polls))
    _system.nodes[node.uuid] = node
    # Create an empty list representing the Node's OTA channel (e.g. 'OTA_MOXA_001')
    _system.ota_channels[node.ota_channel] = []
    return node.to_dict()


def init_endpoint(serial_number, hardware_type, node_uuid, version="1", battery=3000, backlog=0):
    """
    Creates a new Endpoint sensor and links it to an existing parent Node.
    Note: Numeric arguments are cast to int because Robot Framework passes strings.
    """
    if node_uuid not in _system.nodes:
        raise KeyError(f"Cannot attach endpoint: Node '{node_uuid}' does not exist")

    ep = Endpoint(
        serial_number=serial_number,
        hardware_type=hardware_type,
        node_uuid=node_uuid,
        version=str(version),
        battery=int(battery),
        backlog=int(backlog),
    )
    # Save the Endpoint in the system and register its serial number under the parent Node
    _system.endpoints[ep.serial_number] = ep
    _system.nodes[node_uuid].attach_endpoint(ep.serial_number)
    return ep.to_dict()


def init_node_with_default_endpoints(uuid, node_version="33", ep_version="1", battery=3000, backlog=0):
    """
    Helper to quickly build a full Node setup: 1 Node paired with 3 Endpoints
    (one EP1, one EP2, and one Canary_A) as defined in the system rules.
    """
    init_node(uuid=uuid, version=node_version)
    for ep_type in ("EP1", "EP2", "Canary_A"):
        serial = f"{uuid}_{ep_type}"
        init_endpoint(
            serial_number=serial,
            hardware_type=ep_type,
            node_uuid=uuid,
            version=ep_version,
            battery=battery,
            backlog=backlog,
        )
    return api_get_node_by_uuid(uuid)


def tick_ota(uuid):
    """Simulates a single polling cycle where the Node checks its OTA channel for updates."""
    if uuid not in _system.nodes:
        raise KeyError(f"Node '{uuid}' not found")
    node = _system.nodes[uuid]
    # Fetch the list of artifacts currently sitting in this Node's OTA channel
    artifacts = _system.ota_channels.get(node.ota_channel, [])
    return node.poll_ota(artifacts)


def poll_ota_until_done(uuid, max_retries=5):
    """
    Simulates a polling loop with retries (up to max_retries).
    Stops early and returns True as soon as the Node updates, or False if an error is detected.
    """
    if uuid not in _system.nodes:
        raise KeyError(f"Node '{uuid}' not found")
    node = _system.nodes[uuid]

    # '_' is used as the loop variable because we don't need the index number itself
    for _ in range(int(max_retries)):
        updated = tick_ota(uuid)
        if updated:
            return True
        # No point in retrying if the artifact has a hardware mismatch or bad format
        if node.last_error:
            return False
    return False


def set_endpoint_backlog(serial_number, backlog):
    """Sets the number of pending samples (backlog) on a specific Endpoint."""
    if serial_number not in _system.endpoints:
        raise KeyError(f"Endpoint '{serial_number}' not found")
    _system.endpoints[serial_number].backlog = max(0, int(backlog))


def drain_endpoint_backlog(serial_number, amount=None):
    """
    Simulates uploading pending samples from the Endpoint to clear its backlog.
    Drains all samples if amount is None, or a specific amount if provided.
    """
    if serial_number not in _system.endpoints:
        raise KeyError(f"Endpoint '{serial_number}' not found")
    drain_amount = None if amount is None else int(amount)
    return _system.endpoints[serial_number].drain_backlog(drain_amount)


def set_endpoint_battery(serial_number, battery):
    """Updates the battery level (in mA) of a specific Endpoint."""
    if serial_number not in _system.endpoints:
        raise KeyError(f"Endpoint '{serial_number}' not found")
    _system.endpoints[serial_number].battery = int(battery)


def trigger_endpoint_dfu(serial_number, target_version):
    """Triggers a firmware update (DFU) attempt on the given Endpoint."""
    if serial_number not in _system.endpoints:
        raise KeyError(f"Endpoint '{serial_number}' not found")
    return _system.endpoints[serial_number].attempt_dfu(str(target_version))