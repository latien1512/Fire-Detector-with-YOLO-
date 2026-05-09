from gpiozero import OutputDevice

# ================= CONFIG =================

RELAY_PINS = {
    "buzzer": 22,
    "fan": 27,
    "mist": 17,
    "emergency": 26,
}

ACTIVE_HIGH = True

_devices = {}
_initialized = False


# ================= SETUP =================

def setup_relays() -> None:
    global _initialized

    if _initialized:
        return

    for name, pin in RELAY_PINS.items():
        _devices[name] = OutputDevice(
            pin,
            active_high=ACTIVE_HIGH,
            initial_value=False
        )

    _initialized = True

# ================= WRITE =================

def write_relay(name: str, is_on: bool) -> None:
    if not _initialized:
        setup_relays()

    if name not in _devices:
        raise ValueError(f"Unknown relay name: {name}")

    if is_on:
        _devices[name].on()
    else:
        _devices[name].off()


def write_actuators(actuator: dict) -> None:
    """
    actuator expected:
    {
        "buzzer": bool,
        "fan": bool,
        "mist": bool,
        "emergency": bool
    }
    """
    if not _initialized:
        setup_relays()

    for name in RELAY_PINS:
        write_relay(name, bool(actuator.get(name, False)))


# ================= UTIL =================

def all_off() -> None:
    for name in RELAY_PINS:
        write_relay(name, False)


def cleanup_relays() -> None:
    global _initialized

    if _initialized:
        try:
            all_off()
        finally:
            for dev in _devices.values():
                dev.close()
            _initialized = False