# Augury Home Assignment – IoT Validation & Signal Processing

End-to-end automated validation suite for a simulated Augury IoT system (Nodes, Endpoints, OTA firmware updates, and DFU gating rules) implemented in Python and Robot Framework, followed by vibration signal processing analysis.

---

## Project Structure

```text
augury-home-assignment/
├── src/
│   ├── __init__.py           # empty, only neede for the package
│   ├── models.py             # Domain models (Node, Endpoint, IoTSystem)
│   └── augury_api.py         # Simulated Augury API and Robot Framework test helpers
├── tests/
│   └── iot_validation.robot  # End-to-end Robot Framework test suite
├── requirements.txt
└── README.md
```

---

## Setup & Installation

1. Create and activate a Python virtual environment:
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

2. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```

---

## Running the Tests

Run the Robot Framework test suite from the project root directory:
```powershell
robot tests/iot_validation.robot
```

Running the suite executes all test cases and generates `report.html`, `log.html`, and `output.xml` locally (excluded from Git via `.gitignore`).

---

## Architecture & Design Decisions

### 1. Domain Modeling (`src/models.py`)
* **`Node`:** Parses its `uuid` (`<hardware_type>_<string>`) upon initialization to automatically derive `hardware_type` (`AHN2`, `Cassia`, `Moxa`), `api_host` (`moxa_api.azure` for Moxa; `buildroot_api.azure` for AHN2/Cassia), and `ota_channel` (`OTA_<uuid>`). This guarantees valid, consistent configuration across entities.
* **`Endpoint`:** Encapsulates sensor state (`serial_number`, `hardware_type`, `node_uuid`, `version`, `battery`, `backlog`) and enforces hardware-specific DFU battery thresholds (`2500 mA` for `EP1`/`EP2`, `3600 mA` for `Canary_A`).
* **`IoTSystem`:** Holds the in-memory state of all Nodes, Endpoints, and OTA channels across test steps. Reset via `Test Setup` and `Test Teardown` (`Reset System`) to ensure full isolation between test cases.

### 2. Documented Behavioral Choices
* **OTA Polling & Retries:** Posting an artifact to `OTA_<uuid>` queues it in the channel without updating the Node immediately. The Node polls its channel via `tick_ota` / `poll_ota_until_done` and transitions to the target version only after **`3` consecutive valid poll cycles** (`required_polls = 3`).
* **OTA Error Surfacing:** Artifact validation checks the `.swu` format and compares hardware types case-insensitively (e.g., `moxa_34.swu` matches `MOXA_...`). When a mismatched artifact is posted (e.g., `moxa_34.swu` on a `Cassia` Node), the Node rejects the update, keeps its existing version, stops retrying, and records a descriptive error message in `last_error`.
* **Endpoint Backlog Draining:** An Endpoint with `backlog > 0` blocks any DFU attempt. The helper `drain_endpoint_backlog` simulates uploading queued sensor samples to clear the backlog (`0`), allowing subsequent DFU attempts to succeed once battery requirements are also met.

### 3. Test Setup & Simulation Helpers (`src/augury_api.py`)
In addition to the 4 core API functions (`api_get_endpoint_by_serial`, `api_get_node_by_uuid`, `api_post_version_to_ota_channel`, `api_clear_ota_channel`), the following helper keywords are exposed to Robot Framework to manage test state and simulate system events:

* **`reset_system()`**: Clears all Nodes, Endpoints, and OTA channels from in-memory state (used in `Test Setup` and `Test Teardown`).
* **`init_node(uuid, version="33", required_polls=3)`**: Instantiates a new Node, registers it in the system, and initializes its `OTA_<uuid>` channel.
* **`init_endpoint(serial_number, hardware_type, node_uuid, version="1", battery=3000, backlog=0)`**: Creates an Endpoint sensor and attaches it to an existing parent Node.
* **`init_node_with_default_endpoints(uuid, node_version="33", ep_version="1", battery=3000, backlog=0)`**: Convenience setup helper that creates a Node pre-paired with 3 default Endpoints (`EP1`, `EP2`, and `Canary_A`).
* **`tick_ota(uuid)`**: Advances the Node's OTA polling loop by a single cycle against its channel queue.
* **`poll_ota_until_done(uuid, max_retries=5)`**: Polls repeatedly up to `max_retries`, exiting early on a successful update or immediately upon detecting an artifact validation error (`last_error`).
* **`set_endpoint_backlog(serial_number, backlog)`**: Sets the number of pending samples (`backlog`) on a specific Endpoint.
* **`drain_endpoint_backlog(serial_number, amount=None)`**: Simulates uploading pending samples from the Endpoint, draining all samples by default (`0`) or a specified amount.
* **`set_endpoint_battery(serial_number, battery)`**: Updates the battery level (in `mA`) of a specific Endpoint.
* **`trigger_endpoint_dfu(serial_number, target_version)`**: Triggers a DFU attempt on the Endpoint, enforcing both `backlog == 0` and hardware-specific battery thresholds.