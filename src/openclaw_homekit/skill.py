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
