*** Settings ***
Documentation     End-to-End validation suite for the simulated Augury IoT system.
...               Tests Node OTA updates, hardware artifact validation, and Endpoint DFU gating rules.

# Import our Python fake API directly as a Robot Framework keyword library
Library           ../src/augury_api.py

# Wipe in-memory state before and after each test so tests never affect one another
Test Setup        Reset System
Test Teardown     Reset System


*** Variables ***
${MOXA_UUID}          MOXA_TBCDB1045001
${CASSIA_UUID}        Cassia_NODE002
${AHN2_UUID}          AHN2_NODE003


*** Test Cases ***
TC1: Node OTA Happy Flow With Polling
    [Documentation]    Verify that a Node updates its version only after polling/retries complete
    ...                when a matching hardware artifact (case-insensitive) is posted to its OTA channel.
    # Setup: Create a Moxa Node at version 33 paired with its 3 Endpoints
    ${node}=       Init Node With Default Endpoints    ${MOXA_UUID}    node_version=33
    ${channel}=    Set Variable    ${node}[ota_channel]

    # Action 1: Upload matching artifact ('moxa' lowercase matches 'MOXA' UUID)
    ${status}=    Api Post Version To Ota Channel    ${channel}    moxa_34.swu
    Should Be Equal As Integers    ${status}    200

    # Assertion 1: Verify Node does NOT update instantly after only 1 poll cycle
    ${updated_early}=    Tick Ota    ${MOXA_UUID}
    Should Not Be True    ${updated_early}
    #Our own keyword
    Node Version Should Be    ${MOXA_UUID}    33

    # Action 2 & Assertion 2: Complete polling retries and verify Node updates to version 34
    ${updated}=    Poll Ota Until Done    ${MOXA_UUID}    max_retries=5
    Should Be True    ${updated}
    #Our own keyword
    Node Version Should Be    ${MOXA_UUID}    34
    Node Should Have No Error    ${MOXA_UUID}


TC2A: Endpoint DFU Blocked By Backlog Until Drained
    [Documentation]    Verify that Endpoint DFU is blocked while pending samples (backlog > 0) exist,
    ...                and proceeds once the backlog drains to 0.
    # Setup: Create a Node and an EP1 sensor with 10 pending samples in backlog
    Init Node    ${AHN2_UUID}    version=33
    ${ep_serial}=    Set Variable    ${AHN2_UUID}_EP1
    Init Endpoint    ${ep_serial}    EP1    ${AHN2_UUID}    version=1    battery=3000    backlog=10

    # Action 1 & Assertion 1: Trigger DFU while backlog > 0 -> must be blocked
    ${dfu_started}=    Trigger Endpoint Dfu    ${ep_serial}    2
    Should Not Be True    ${dfu_started}
    Endpoint Version Should Be    ${ep_serial}    1

    # Action 2: Drain pending samples to 0
    ${remaining}=    Drain Endpoint Backlog    ${ep_serial}
    Should Be Equal As Integers    ${remaining}    0

    # Action 3 & Assertion 2: Retry DFU now that backlog is 0 -> must succeed
    ${dfu_succeeded}=    Trigger Endpoint Dfu    ${ep_serial}    2
    Should Be True    ${dfu_succeeded}
    Endpoint Version Should Be    ${ep_serial}    2


TC2B: Endpoint DFU Deferred When Battery Below Threshold
    [Documentation]    Verify that DFU is deferred when battery is below the hardware-specific threshold
    ...                (2500mA for EP1/EP2, 3600mA for Canary_A).
    # Setup: Create Node with EP2 (threshold 2500mA) and Canary_A (threshold 3600mA)
    Init Node    ${AHN2_UUID}    version=33
    ${ep2_serial}=       Set Variable    ${AHN2_UUID}_EP2
    ${canary_serial}=    Set Variable    ${AHN2_UUID}_Canary_A

    # Initialize EP2 at 2400mA (< 2500mA) and Canary_A at 3000mA (< 3600mA)
    Init Endpoint    ${ep2_serial}       EP2         ${AHN2_UUID}    version=1    battery=2400    backlog=0
    Init Endpoint    ${canary_serial}    Canary_A    ${AHN2_UUID}    version=1    battery=3000    backlog=0

    # Action & Assertion 1: Both sensors must defer DFU due to insufficient battery
    ${ep2_updated}=       Trigger Endpoint Dfu    ${ep2_serial}       2
    ${canary_updated}=    Trigger Endpoint Dfu    ${canary_serial}    2
    Should Not Be True    ${ep2_updated}
    Should Not Be True    ${canary_updated}
    Endpoint Version Should Be    ${ep2_serial}       1
    Endpoint Version Should Be    ${canary_serial}    1

    # Action & Assertion 2: Charge Canary_A to exact threshold (3600mA) and verify DFU succeeds
    Set Endpoint Battery    ${canary_serial}    3600
    ${canary_updated_after_charge}=    Trigger Endpoint Dfu    ${canary_serial}    2
    Should Be True    ${canary_updated_after_charge}
    Endpoint Version Should Be    ${canary_serial}    2


TC3: Bad Firmware OTA Rejected With Error
    [Documentation]    Verify that posting an artifact for a different hardware type (e.g. Moxa artifact
    ...                on a Cassia Node) fails OTA, keeps version unchanged, and reports an error.
    # Setup: Create a Cassia Node at version 33
    ${node}=       Init Node With Default Endpoints    ${CASSIA_UUID}    node_version=33
    ${channel}=    Set Variable    ${node}[ota_channel]

    # Action: Upload a Moxa firmware artifact to the Cassia OTA channel
    ${status}=     Api Post Version To Ota Channel    ${channel}    moxa_34.swu
    Should Be Equal As Integers    ${status}    200
    ${updated}=    Poll Ota Until Done    ${CASSIA_UUID}    max_retries=5

    # Assertion: Update must fail, version remains 33, and an error is recorded
    Should Not Be True    ${updated}
    #Our own keywords again
    Node Version Should Be    ${CASSIA_UUID}    33
    Node Should Report Hardware Mismatch Error    ${CASSIA_UUID}


*** Keywords ***
Node Version Should Be
    [Arguments]    ${uuid}    ${expected_version}
    ${node}=    Api Get Node By Uuid    ${uuid}
    Should Be Equal As Strings    ${node}[version]    ${expected_version}

Node Should Have No Error
    [Arguments]    ${uuid}
    ${node}=    Api Get Node By Uuid    ${uuid}
    Should Be Empty    ${node}[last_error]

Node Should Report Hardware Mismatch Error
    [Arguments]    ${uuid}
    ${node}=    Api Get Node By Uuid    ${uuid}
    Should Not Be Empty    ${node}[last_error]
    Should Contain    ${node}[last_error]    Hardware mismatch

Endpoint Version Should Be
    [Arguments]    ${serial}    ${expected_version}
    ${ep}=    Api Get Endpoint By Serial    ${serial}
    Should Be Equal As Strings    ${ep}[version]    ${expected_version}