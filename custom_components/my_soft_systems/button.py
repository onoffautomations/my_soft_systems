from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiohttp import ClientSession, ClientError
from yarl import URL

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    CONF_HUB_IP,
    CONF_HUB_PORT,
    CONF_DOOR_ID,
    CONF_DOOR_NAME,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    data = {**entry.data, **entry.options}
    door_name: str = data[CONF_DOOR_NAME]
    door_id: str = data[CONF_DOOR_ID]
    hub_ip: str = data[CONF_HUB_IP]
    hub_port: int = data[CONF_HUB_PORT]

    session: ClientSession = async_get_clientsession(hass)

    device_info = DeviceInfo(
        identifiers={(DOMAIN, entry.unique_id)},
        name=door_name,
        manufacturer="OnOff Automations",
        model="My Soft Systems Hub",
        configuration_url=f"http://{hub_ip}:{hub_port}/",
    )

    base = URL.build(scheme="http", host=hub_ip, port=hub_port) / "admin" / "Door" / door_id

    # Icons:
    # - Prefer turnstile icons; HA/MDI have `mdi:turnstile` and `mdi:turnstile-outline`.
    # - If your HA theme doesn’t include them yet, they’ll fall back to generic gate icons.
    def _icon(primary: str, fallback: str) -> str:
        # HA will simply show a generic icon if primary doesn't exist;
        # we still return primary here. Fallback kept for clarity.
        return primary or fallback

    entities: list[ButtonEntity] = [
        _MSSDoorButton(
            entry,
            session,
            name="Open till next schedule",               # no dash or door prefix
            url=base / "true" / "false",
            key="open_until_next",
            icon=_icon("mdi:turnstile", "mdi:gate-open"),
            device_info=device_info,
        ),
        _MSSDoorButton(
            entry,
            session,
            name="Close Back to Schule",                   # no dash or door prefix
            url=base / "true" / "true",
            key="close_back_to_schedule",
            icon=_icon("mdi:turnstile-outline", "mdi:gate"),
            device_info=device_info,
        ),
        _MSSDoorButton(
            entry,
            session,
            name="Open for 1 Entry",                       # no dash or door prefix
            url=base / "false" / "false",
            key="open_one_entry",
            icon=_icon("mdi:turnstile", "mdi:numeric-1-circle"),
            device_info=device_info,
        ),
        _MSSDoorButton(
            entry,
            session,
            name="Close if open for 1 entry",              # no dash or door prefix
            url=base / "false" / "true",
            key="close_if_single_open",
            icon=_icon("mdi:turnstile-outline", "mdi:close-thick"),
            device_info=device_info,
        ),
    ]

    async_add_entities(entities, update_before_add=False)


class _MSSDoorButton(ButtonEntity):
    """A stateless button that calls the hub endpoint."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        entry: ConfigEntry,
        session: ClientSession,
        name: str,
        url: URL,
        key: str,
        icon: str,
        device_info: DeviceInfo,
    ) -> None:
        self._entry = entry
        self._session = session
        self._url = str(url)
        self._key = key
        self._attr_name = name            # clean names (no leading dash or door prefix)
        self._attr_unique_id = f"{entry.unique_id}:{key}"
        self._attr_icon = icon
        self._attr_device_info = device_info
        self._last_status: str | None = None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"last_result": self._last_status}

    async def async_press(self) -> None:
        """Call the configured endpoint."""
        try:
            async with asyncio.timeout(10):
                async with self._session.get(self._url) as resp:
                    text = await resp.text()
                    if resp.status == 200:
                        self._last_status = f"OK ({resp.status})"
                        _LOGGER.debug("MSS door action '%s' ok: %s", self._key, text)
                    else:
                        self._last_status = f"HTTP {resp.status}: {text[:200]}"
                        _LOGGER.warning("MSS door action '%s' failed: %s %s", self._key, resp.status, text)
        except asyncio.TimeoutError as err:
            self._last_status = "Error: Request timed out after 10 seconds"
            _LOGGER.error(
                "MSS door action '%s' timeout - URL: %s - Error: %s",
                self._key,
                self._url,
                type(err).__name__
            )
        except ClientError as err:
            self._last_status = f"Error: {type(err).__name__} - {err}"
            _LOGGER.error(
                "MSS door action '%s' client error - URL: %s - Error type: %s - Details: %s",
                self._key,
                self._url,
                type(err).__name__,
                str(err) if str(err) else "No error details available"
            )
        except Exception as err:
            self._last_status = f"Unexpected error: {type(err).__name__} - {err}"
            _LOGGER.exception(
                "MSS door action '%s' unexpected error - URL: %s",
                self._key,
                self._url
            )
        self.async_write_ha_state()
