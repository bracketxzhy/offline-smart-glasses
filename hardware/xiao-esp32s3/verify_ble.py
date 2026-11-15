"""Verify the physical board's BLE discovery, GATT reads/writes and reconnection."""
import asyncio
import json
import sys
from pathlib import Path

from bleak import BleakClient, BleakScanner

NAME = "XIAO-S3-1984"
SERVICE = "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
CHARACTERISTIC = "beb5483e-36e1-4688-b7f5-ea07361b26a8"


async def verify():
    device = await BleakScanner.find_device_by_name(NAME, timeout=15)
    assert device is not None, f"Expected BLE device {NAME!r} was not discovered"
    report = {"name": NAME, "address": device.address, "rounds": []}
    for attempt in range(2):
        if attempt:
            device = await BleakScanner.find_device_by_name(NAME, timeout=15)
            assert device is not None, "Board did not resume advertising after disconnect"
        async with BleakClient(device, timeout=20) as client:
            assert client.services.get_service(SERVICE), "Expected GATT service is missing"
            initial = bytes(await client.read_gatt_char(CHARACTERISTIC))
            payload = f"xiao-ble-round-{attempt + 1}".encode()
            await client.write_gatt_char(CHARACTERISTIC, payload, response=True)
            received = bytes(await client.read_gatt_char(CHARACTERISTIC))
            assert received == payload, f"BLE readback mismatch: {received!r}"
            report["rounds"].append({"initial": initial.decode(errors="replace"),
                                     "written": payload.decode(),
                                     "readback": received.decode(), "passed": True})
        await asyncio.sleep(1)
    return report


if __name__ == "__main__":
    try:
        result = asyncio.run(verify())
    except Exception as exc:
        result = {"passed": False, "error": f"{type(exc).__name__}: {exc}"}
        code = 1
    else:
        result["passed"] = True
        code = 0
    output = json.dumps(result, ensure_ascii=False, indent=2)
    print(output)
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(output + "\n", encoding="utf-8")
    sys.exit(code)
