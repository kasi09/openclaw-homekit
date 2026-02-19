"""HomeKit Skill - Direct HomeKit device control via aiohomekit."""

import asyncio
import threading
from typing import Any

from aiohomekit import Controller
from aiohomekit.model import Accessories
from openclaw_python_skill.skill import Skill


class HomeKitSkill(Skill):
    """Control HomeKit devices directly via the HomeKit Accessory Protocol.

    Uses aiohomekit for native HomeKit communication without requiring
    Homebridge or Home Assistant as middleware.

    Provides actions for:
    - discover: Find HomeKit devices on the local network
    - pair: Pair with a HomeKit device using its PIN
    - unpair: Remove a pairing with a device
    - list_accessories: List all accessories and services for a paired device
    - get_characteristic: Read a characteristic value
    - set_characteristic: Write a characteristic value
    - list_pairings: List all stored pairings
    - identify: Trigger device identification (blink/beep)
    - get_all_characteristics: Read all characteristics for a device at once
    - set_multiple: Set multiple characteristics in one call
    - get_device_info: Get device manufacturer, model, serial, firmware info
    - device_summary: Human-readable summary of all paired devices
    - health_check: Check reachability of all paired devices
    """

    def __init__(self, pairing_file: str = "homekit_pairings.json") -> None:
        super().__init__(name="homekit", version="1.0.0")
        self.pairing_file = pairing_file
        self._controller: Controller | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        """Ensure background event loop is running and return it."""
        if self._loop is not None and self._loop.is_running():
            return self._loop

        loop = asyncio.new_event_loop()
        thread = threading.Thread(target=loop.run_forever, daemon=True)
        thread.start()
        self._loop = loop
        self._thread = thread
        return loop

    def _run_async(self, coro: Any) -> Any:
        """Submit a coroutine to the background event loop and wait for result."""
        loop = self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=60)

    def _get_controller(self) -> Controller:
        """Get or create the aiohomekit Controller instance."""
        if self._controller is None:
            self._controller = Controller()
            self._controller.load_data(self.pairing_file)
        return self._controller

    def _save_pairings(self) -> None:
        """Save current pairings to the JSON file."""
        if self._controller is None:
            return
        self._controller.save_data(self.pairing_file)

    def process(self, action: str, parameters: dict[str, Any]) -> dict[str, Any]:
        if action == "discover":
            return self._discover(parameters)
        elif action == "pair":
            return self._pair(parameters)
        elif action == "unpair":
            return self._unpair(parameters)
        elif action == "list_accessories":
            return self._list_accessories(parameters)
        elif action == "get_characteristic":
            return self._get_characteristic(parameters)
        elif action == "set_characteristic":
            return self._set_characteristic(parameters)
        elif action == "list_pairings":
            return self._list_pairings()
        elif action == "identify":
            return self._identify(parameters)
        elif action == "get_all_characteristics":
            return self._get_all_characteristics(parameters)
        elif action == "set_multiple":
            return self._set_multiple(parameters)
        elif action == "get_device_info":
            return self._get_device_info(parameters)
        elif action == "device_summary":
            return self._device_summary()
        elif action == "health_check":
            return self._health_check()
        else:
            raise ValueError(f"Unknown action: {action}")

    def _discover(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """Discover HomeKit devices on the local network."""
        timeout = parameters.get("timeout", 10)

        async def _do_discover() -> list[dict[str, Any]]:
            controller = self._get_controller()
            discoveries = await controller.discover(timeout=timeout)  # type: ignore[attr-defined]
            devices = []
            for discovery in discoveries:
                info = discovery.info
                devices.append(
                    {
                        "name": info.get("name", ""),
                        "id": info.get("id", ""),
                        "model": info.get("md", ""),
                        "config_num": info.get("c#", 0),
                        "state_num": info.get("s#", 0),
                        "category": info.get("ci", 0),
                        "status_flags": info.get("sf", 0),
                    }
                )
            return devices

        devices = self._run_async(_do_discover())
        return {"devices": devices, "count": len(devices)}

    def _pair(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """Pair with a HomeKit device."""
        device_id = parameters.get("device_id")
        if not device_id:
            raise ValueError("Missing required parameter: device_id")
        pin = parameters.get("pin")
        if not pin:
            raise ValueError("Missing required parameter: pin")

        async def _do_pair() -> Any:
            controller = self._get_controller()
            pairing = await controller.pair(device_id, pin)  # type: ignore[attr-defined]
            accessories = await pairing.list_accessories_and_characteristics()
            return accessories

        accessories = self._run_async(_do_pair())
        self._save_pairings()

        acc_list = self._format_accessories(accessories)
        return {
            "device_id": device_id,
            "success": True,
            "accessories": acc_list,
        }

    def _unpair(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """Remove a pairing with a device."""
        device_id = parameters.get("device_id")
        if not device_id:
            raise ValueError("Missing required parameter: device_id")

        async def _do_unpair() -> None:
            controller = self._get_controller()
            if device_id not in controller.pairings:
                raise ValueError(f"No pairing found for device: {device_id}")
            await controller.pairings[device_id].close()
            del controller.pairings[device_id]

        self._run_async(_do_unpair())
        self._save_pairings()
        return {"device_id": device_id, "success": True}

    def _list_accessories(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """List all accessories and services for a paired device."""
        device_id = parameters.get("device_id")
        if not device_id:
            raise ValueError("Missing required parameter: device_id")

        async def _do_list() -> Any:
            controller = self._get_controller()
            if device_id not in controller.pairings:
                raise ValueError(f"No pairing found for device: {device_id}")
            pairing = controller.pairings[device_id]
            return await pairing.list_accessories_and_characteristics()

        accessories = self._run_async(_do_list())
        acc_list = self._format_accessories(accessories)
        return {"device_id": device_id, "accessories": acc_list}

    def _get_characteristic(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """Read a characteristic value."""
        device_id = parameters.get("device_id")
        if not device_id:
            raise ValueError("Missing required parameter: device_id")
        aid = parameters.get("aid")
        if aid is None:
            raise ValueError("Missing required parameter: aid")
        iid = parameters.get("iid")
        if iid is None:
            raise ValueError("Missing required parameter: iid")

        async def _do_get() -> Any:
            controller = self._get_controller()
            if device_id not in controller.pairings:
                raise ValueError(f"No pairing found for device: {device_id}")
            pairing = controller.pairings[device_id]
            return await pairing.get_characteristics([(int(aid), int(iid))])

        chars = self._run_async(_do_get())
        key = (int(aid), int(iid))
        value = chars.get(key, {}).get("value")
        return {
            "device_id": device_id,
            "aid": int(aid),
            "iid": int(iid),
            "value": value,
        }

    def _set_characteristic(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """Write a characteristic value."""
        device_id = parameters.get("device_id")
        if not device_id:
            raise ValueError("Missing required parameter: device_id")
        aid = parameters.get("aid")
        if aid is None:
            raise ValueError("Missing required parameter: aid")
        iid = parameters.get("iid")
        if iid is None:
            raise ValueError("Missing required parameter: iid")
        if "value" not in parameters:
            raise ValueError("Missing required parameter: value")
        value = parameters["value"]

        async def _do_set() -> None:
            controller = self._get_controller()
            if device_id not in controller.pairings:
                raise ValueError(f"No pairing found for device: {device_id}")
            pairing = controller.pairings[device_id]
            await pairing.put_characteristics([(int(aid), int(iid), value)])

        self._run_async(_do_set())
        return {
            "device_id": device_id,
            "aid": int(aid),
            "iid": int(iid),
            "value": value,
            "success": True,
        }

    def _list_pairings(self) -> dict[str, Any]:
        """List all stored pairings."""
        controller = self._get_controller()
        pairings = [{"device_id": alias} for alias in controller.aliases]
        return {"pairings": pairings, "count": len(pairings)}

    def _identify(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """Trigger device identification (blink/beep)."""
        device_id = parameters.get("device_id")
        if not device_id:
            raise ValueError("Missing required parameter: device_id")

        async def _do_identify() -> None:
            controller = self._get_controller()
            if device_id not in controller.pairings:
                raise ValueError(f"No pairing found for device: {device_id}")
            pairing = controller.pairings[device_id]
            await pairing.identify()

        self._run_async(_do_identify())
        return {"device_id": device_id, "identified": True}

    def _get_all_characteristics(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """Read all characteristics for a device at once."""
        device_id = parameters.get("device_id")
        if not device_id:
            raise ValueError("Missing required parameter: device_id")

        async def _do_get_all() -> dict[str, Any]:
            controller = self._get_controller()
            if device_id not in controller.pairings:
                raise ValueError(f"No pairing found for device: {device_id}")
            pairing = controller.pairings[device_id]
            accessories = await pairing.list_accessories_and_characteristics()

            targets: list[tuple[int, int]] = []
            if isinstance(accessories, Accessories):
                for acc in accessories:
                    for svc in acc.services:
                        for char in svc.characteristics:
                            targets.append((acc.aid, char.iid))
            elif isinstance(accessories, list):
                for acc in accessories:
                    for svc in acc.get("services", []):
                        for char in svc.get("characteristics", []):
                            aid = acc.get("aid")
                            iid = char.get("iid")
                            if aid is not None and iid is not None:
                                targets.append((int(aid), int(iid)))

            if not targets:
                return {"characteristics": [], "count": 0}

            chars = await pairing.get_characteristics(targets)
            result_list = [
                {"aid": aid, "iid": iid, "value": data.get("value")}
                for (aid, iid), data in chars.items()
            ]
            return {"characteristics": result_list, "count": len(result_list)}

        result = self._run_async(_do_get_all())
        return {"device_id": device_id, **result}

    def _set_multiple(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """Set multiple characteristics in one call."""
        device_id = parameters.get("device_id")
        if not device_id:
            raise ValueError("Missing required parameter: device_id")
        characteristics = parameters.get("characteristics")
        if not characteristics or not isinstance(characteristics, list):
            raise ValueError("Missing required parameter: characteristics")

        targets: list[tuple[int, int, Any]] = []
        for char in characteristics:
            if not isinstance(char, dict):
                raise ValueError("Each characteristic must be a dict with aid, iid, value")
            aid = char.get("aid")
            iid = char.get("iid")
            if aid is None or iid is None or "value" not in char:
                raise ValueError("Each characteristic must have aid, iid, and value")
            targets.append((int(aid), int(iid), char["value"]))

        async def _do_set_multiple() -> None:
            controller = self._get_controller()
            if device_id not in controller.pairings:
                raise ValueError(f"No pairing found for device: {device_id}")
            pairing = controller.pairings[device_id]
            await pairing.put_characteristics(targets)

        self._run_async(_do_set_multiple())
        return {"device_id": device_id, "count": len(targets), "success": True}

    def _get_device_info(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """Get device information from the AccessoryInformation service."""
        device_id = parameters.get("device_id")
        if not device_id:
            raise ValueError("Missing required parameter: device_id")

        # HAP characteristic type short codes for AccessoryInformation
        char_map = {
            "20": "manufacturer",
            "21": "model",
            "23": "name",
            "30": "serial_number",
            "52": "firmware_revision",
            "53": "hardware_revision",
        }

        async def _do_get_info() -> dict[str, str]:
            controller = self._get_controller()
            if device_id not in controller.pairings:
                raise ValueError(f"No pairing found for device: {device_id}")
            pairing = controller.pairings[device_id]
            accessories = await pairing.list_accessories_and_characteristics()
            info: dict[str, str] = {}

            if isinstance(accessories, Accessories):
                for acc in accessories:
                    for svc in acc.services:
                        if "3E" in str(svc.type).upper():
                            for char in svc.characteristics:
                                char_type = str(char.type).upper()
                                for key, field in char_map.items():
                                    if key.upper() in char_type:
                                        info[field] = str(char.value or "")
            elif isinstance(accessories, list):
                for acc in accessories:
                    for svc in acc.get("services", []):
                        if "3E" in str(svc.get("type", "")).upper():
                            for char in svc.get("characteristics", []):
                                char_type = str(char.get("type", "")).upper()
                                for key, field in char_map.items():
                                    if key.upper() in char_type:
                                        info[field] = str(char.get("value", ""))

            return info

        info = self._run_async(_do_get_info())
        return {
            "device_id": device_id,
            "manufacturer": info.get("manufacturer", ""),
            "model": info.get("model", ""),
            "name": info.get("name", ""),
            "serial_number": info.get("serial_number", ""),
            "firmware_revision": info.get("firmware_revision", ""),
            "hardware_revision": info.get("hardware_revision", ""),
        }

    def _device_summary(self) -> dict[str, Any]:
        """Human-readable summary of all paired devices."""
        controller = self._get_controller()
        devices: list[dict[str, Any]] = []

        for alias in controller.aliases:
            device_info: dict[str, Any] = {
                "device_id": alias,
                "services": [],
                "reachable": True,
            }
            try:
                if alias in controller.pairings:
                    pairing = controller.pairings[alias]
                    accessories = self._run_async(pairing.list_accessories_and_characteristics())
                    acc_list = self._format_accessories(accessories)
                    service_types = []
                    for acc in acc_list:
                        for svc in acc.get("services", []):
                            service_types.append(svc.get("type", "unknown"))
                    device_info["services"] = service_types
                    device_info["accessory_count"] = len(acc_list)
            except Exception:
                device_info["reachable"] = False
            devices.append(device_info)

        return {"devices": devices, "count": len(devices)}

    def _health_check(self) -> dict[str, Any]:
        """Check reachability of all paired HomeKit devices."""
        controller = self._get_controller()
        results: list[dict[str, Any]] = []

        for alias in controller.aliases:
            status: dict[str, Any] = {"device_id": alias, "reachable": False}
            try:
                if alias in controller.pairings:
                    pairing = controller.pairings[alias]
                    self._run_async(pairing.list_accessories_and_characteristics())
                    status["reachable"] = True
            except Exception as e:
                status["error"] = str(e)
            results.append(status)

        reachable_count = sum(1 for r in results if r["reachable"])
        return {
            "devices": results,
            "total": len(results),
            "reachable": reachable_count,
            "unreachable": len(results) - reachable_count,
        }

    @staticmethod
    def _format_accessories(accessories: Any) -> list[dict[str, Any]]:
        """Format accessories data into a serializable list."""
        if isinstance(accessories, Accessories):
            acc_list: list[dict[str, Any]] = []
            for acc in accessories:
                services = []
                for svc in acc.services:
                    chars = []
                    for char in svc.characteristics:
                        chars.append(
                            {
                                "iid": char.iid,
                                "type": str(char.type),
                                "description": char.description or "",
                                "value": char.value,
                                "format": str(char.format) if char.format else "",
                                "perms": ([str(p) for p in char.perms] if char.perms else []),
                            }
                        )
                    services.append(
                        {
                            "type": str(svc.type),
                            "characteristics": chars,
                        }
                    )
                acc_list.append(
                    {
                        "aid": acc.aid,
                        "services": services,
                    }
                )
            return acc_list

        # Fallback for raw dict data
        if isinstance(accessories, list):
            return list(accessories)
        if isinstance(accessories, dict) and "accessories" in accessories:
            return list(accessories["accessories"])
        return []
