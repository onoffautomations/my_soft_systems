from __future__ import annotations

import ipaddress
import logging
import voluptuous as vol
from typing import Any

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    DOMAIN,
    CONF_HUB_IP,
    CONF_HUB_PORT,
    CONF_DOOR_ID,
    CONF_DOOR_NAME,
    CONF_DB_HOST,
    CONF_DB_PORT,
    CONF_DB_NAME,
    CONF_DB_USER,
    CONF_DB_PASSWORD,
    DEFAULT_PORT,
    DEFAULT_HUB_HOST,
    DEFAULT_DB_HOST,
    DEFAULT_DB_PORT,
    DEFAULT_DB_NAME,
    DEFAULT_DB_USER,
)

_LOGGER = logging.getLogger(__name__)

TITLE = "My Soft Systems (OnOff Automations)"


def _is_pymssql_available() -> bool:
    """Check if python-tds is available."""
    try:
        import pytds
        return True
    except ImportError:
        return False


async def _fetch_port_from_db(
    hass: HomeAssistant,
    host: str,
    port: int,
    database: str,
    username: str,
    password: str,
) -> int | None:
    """Fetch ServerWebServicePort from SQL Server database using python-tds."""
    try:
        import pytds

        def _query_port():
            """Query port in executor."""
            conn = None
            try:
                # Connect to SQL Server using python-tds
                conn = pytds.connect(
                    server=host,
                    port=port,
                    database=database,
                    user=username,
                    password=password,
                    timeout=10,
                    autocommit=True,
                )
                cursor = conn.cursor()

                # Query ServerWebServicePort from GlobalControl
                query = "SELECT ServerWebServicePort FROM dbo.GlobalControl;"
                cursor.execute(query)

                # Fetch the result
                row = cursor.fetchone()
                if row and row[0]:
                    return int(row[0])
                return None
            except Exception as err:
                _LOGGER.error("Database port query failed: %s", err)
                raise
            finally:
                if conn:
                    conn.close()

        # Run database query in executor to avoid blocking
        return await hass.async_add_executor_job(_query_port)
    except ImportError:
        _LOGGER.error("python-tds not installed")
        return None
    except Exception as err:
        _LOGGER.error("Failed to fetch port: %s", err)
        return None


async def _fetch_doors_from_db(
    hass: HomeAssistant,
    host: str,
    port: int,
    database: str,
    username: str,
    password: str,
) -> list[dict[str, Any]] | None:
    """Fetch doors from SQL Server database using python-tds."""
    try:
        import pytds

        def _query_doors():
            """Query doors in executor."""
            conn = None
            try:
                # Connect to SQL Server using python-tds
                conn = pytds.connect(
                    server=host,
                    port=port,
                    database=database,
                    user=username,
                    password=password,
                    timeout=10,
                    autocommit=True,
                )
                cursor = conn.cursor()

                # Query doors
                query = """
                    SELECT Oid AS DoorId, Description AS DoorName, OutputPort
                    FROM dbo.Door
                    ORDER BY Description;
                """
                cursor.execute(query)

                # Fetch all rows
                rows = cursor.fetchall()

                # Get column names
                columns = [desc[0] for desc in cursor.description]

                # Convert to list of dicts with string keys
                doors = []
                for row in rows:
                    row_dict = dict(zip(columns, row))
                    doors.append({
                        "door_id": str(row_dict["DoorId"]),
                        "door_name": str(row_dict["DoorName"]),
                        "output_port": int(row_dict["OutputPort"]) if row_dict.get("OutputPort") else 0,
                    })

                return doors
            except Exception as err:
                _LOGGER.error("Database query failed: %s", err)
                raise
            finally:
                if conn:
                    conn.close()

        # Run database query in executor to avoid blocking
        return await hass.async_add_executor_job(_query_doors)
    except ImportError:
        _LOGGER.error("python-tds not installed")
        return None
    except Exception as err:
        _LOGGER.error("Failed to fetch doors: %s", err)
        return None


def _is_valid_ip_or_host(value: str) -> bool:
    """Return True if value is an IP address or a simple hostname (no spaces)."""
    v = (value or "").strip()
    if not v or any(ch.isspace() for ch in v):
        return False
    try:
        ipaddress.ip_address(v)
        return True
    except ValueError:
        # Allow simple hostnames like 'mss-hub.local' or 'hub.lan'
        # Disallow empty/whitespace (already handled), otherwise accept.
        return True


class MySoftSystemsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for My Soft Systems."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._mode: str | None = None
        self._hub_ip: str = ""
        self._hub_port: int = DEFAULT_PORT
        self._detected_doors: list[dict[str, Any]] = []
        self._db_config: dict[str, Any] = {}
        self._door_map: dict[str, dict[str, Any]] = {}

    def _user_schema(self, defaults: dict[str, Any] | None = None) -> vol.Schema:
        """Schema for manual door configuration."""
        d = defaults or {}
        return vol.Schema(
            {
                vol.Required(CONF_HUB_IP, default=d.get(CONF_HUB_IP, DEFAULT_HUB_HOST)): cv.string,
                vol.Required(CONF_HUB_PORT, default=d.get(CONF_HUB_PORT, DEFAULT_PORT)): int,
                vol.Required(CONF_DOOR_ID, default=d.get(CONF_DOOR_ID, "")): cv.string,
                vol.Required(CONF_DOOR_NAME, default=d.get(CONF_DOOR_NAME, "")): cv.string,
            }
        )

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle mode selection: auto-detect or manual."""
        # Check if pymssql is available for auto-detect
        pymssql_available = _is_pymssql_available()

        # If python-tds is not available, go straight to manual mode
        if not pymssql_available:
            _LOGGER.warning(
                "python-tds is not available. Auto-detect disabled. "
                "This should not happen as it's in requirements."
            )
            return await self.async_step_manual()

        if user_input is not None:
            self._mode = user_input["mode"]
            if self._mode == "auto":
                return await self.async_step_database()
            else:
                return await self.async_step_manual()

        # Show mode selection
        data_schema = vol.Schema(
            {
                vol.Required("mode", default="auto"): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"label": "Auto-detect from database", "value": "auto"},
                            {"label": "Manual configuration", "value": "manual"},
                        ],
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }
        )

        return self.async_show_form(step_id="user", data_schema=data_schema)

    async def async_step_database(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle database connection for auto-detection."""
        errors: dict[str, str] = {}

        if user_input is None:
            # Show database connection form (hub port will be auto-detected)
            data_schema = vol.Schema(
                {
                    vol.Required(CONF_HUB_IP, default=DEFAULT_HUB_HOST): cv.string,
                    vol.Required(CONF_DB_HOST, default=DEFAULT_DB_HOST): cv.string,
                    vol.Required(CONF_DB_PORT, default=DEFAULT_DB_PORT): int,
                    vol.Required(CONF_DB_NAME, default=DEFAULT_DB_NAME): cv.string,
                    vol.Required(CONF_DB_USER, default=DEFAULT_DB_USER): cv.string,
                    vol.Required(CONF_DB_PASSWORD): cv.string,
                }
            )
            return self.async_show_form(step_id="database", data_schema=data_schema)

        # Validate hub connection details
        hub_ip = (user_input.get(CONF_HUB_IP) or "").strip()

        if not _is_valid_ip_or_host(hub_ip):
            errors[CONF_HUB_IP] = "invalid_host"

        # Validate database connection details
        db_host = (user_input.get(CONF_DB_HOST) or "").strip()
        db_port = user_input.get(CONF_DB_PORT, DEFAULT_DB_PORT)
        db_name = (user_input.get(CONF_DB_NAME) or "").strip()
        db_user = (user_input.get(CONF_DB_USER) or "").strip()
        db_password = user_input.get(CONF_DB_PASSWORD, "")

        if not db_host:
            errors[CONF_DB_HOST] = "required"
        if not db_name:
            errors[CONF_DB_NAME] = "required"
        if not db_user:
            errors[CONF_DB_USER] = "required"
        if not db_password:
            errors[CONF_DB_PASSWORD] = "required"

        try:
            db_port = int(db_port)
            if db_port < 1 or db_port > 65535:
                errors[CONF_DB_PORT] = "invalid_port"
        except (TypeError, ValueError):
            errors[CONF_DB_PORT] = "invalid_port"

        if errors:
            data_schema = vol.Schema(
                {
                    vol.Required(CONF_HUB_IP, default=hub_ip): cv.string,
                    vol.Required(CONF_DB_HOST, default=db_host): cv.string,
                    vol.Required(CONF_DB_PORT, default=db_port): int,
                    vol.Required(CONF_DB_NAME, default=db_name): cv.string,
                    vol.Required(CONF_DB_USER, default=db_user): cv.string,
                    vol.Required(CONF_DB_PASSWORD): cv.string,
                }
            )
            return self.async_show_form(step_id="database", data_schema=data_schema, errors=errors)

        # Auto-detect hub port from database
        hub_port = await _fetch_port_from_db(
            self.hass, db_host, db_port, db_name, db_user, db_password
        )

        if hub_port is None:
            _LOGGER.warning("Could not auto-detect hub port, using default: %s", DEFAULT_PORT)
            hub_port = DEFAULT_PORT
        else:
            _LOGGER.info("Auto-detected hub port from database: %s", hub_port)

        # Try to fetch doors from database
        doors = await _fetch_doors_from_db(
            self.hass, db_host, db_port, db_name, db_user, db_password
        )

        if doors is None or len(doors) == 0:
            errors["base"] = "cannot_connect"
            data_schema = vol.Schema(
                {
                    vol.Required(CONF_HUB_IP, default=hub_ip): cv.string,
                    vol.Required(CONF_DB_HOST, default=db_host): cv.string,
                    vol.Required(CONF_DB_PORT, default=db_port): int,
                    vol.Required(CONF_DB_NAME, default=db_name): cv.string,
                    vol.Required(CONF_DB_USER, default=db_user): cv.string,
                    vol.Required(CONF_DB_PASSWORD): cv.string,
                }
            )
            return self.async_show_form(step_id="database", data_schema=data_schema, errors=errors)

        # Store hub info and detected doors
        self._hub_ip = hub_ip
        self._hub_port = hub_port
        self._detected_doors = doors

        # Proceed to door selection
        return await self.async_step_select_doors()

    async def async_step_select_doors(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle door selection with checkboxes."""
        if user_input is None:
            # Build schema with select all toggle at top
            door_options = {}
            door_map = {}  # Map field names to door data

            # Add select all / deselect all controls at the top
            door_options[vol.Required("import_all_doors", default=True)] = cv.boolean

            for door in self._detected_doors:
                # Use door name as the field key for better readability
                field_name = door["door_name"]
                door_options[vol.Optional(field_name, default=True)] = cv.boolean
                door_map[field_name] = door

            data_schema = vol.Schema(door_options)

            # Store the map for later use
            self._door_map = door_map

            return self.async_show_form(
                step_id="select_doors",
                data_schema=data_schema,
                description_placeholders={
                    "door_count": str(len(self._detected_doors)),
                },
            )

        # Check if user wants to import all doors
        import_all = user_input.get("import_all_doors", False)

        # Get selected doors
        selected_doors = []
        if import_all:
            # Import all detected doors
            selected_doors = self._detected_doors.copy()
        else:
            # Only import checked doors
            for door_name, is_selected in user_input.items():
                if door_name == "import_all_doors":
                    continue
                if is_selected and door_name in self._door_map:
                    selected_doors.append(self._door_map[door_name])

        if not selected_doors:
            return self.async_abort(reason="no_doors_selected")

        # Create entries for all selected doors
        created_count = 0
        skipped_count = 0

        for door in selected_doors:
            door_id = door["door_id"]
            door_name = door["door_name"]
            unique_id = f"{self._hub_ip}:{self._hub_port}:{door_id}"

            # Check if already configured
            existing_entry = None
            for entry in self.hass.config_entries.async_entries(DOMAIN):
                if entry.unique_id == unique_id:
                    existing_entry = entry
                    break

            if existing_entry:
                _LOGGER.info("Door %s already configured, skipping", door_name)
                skipped_count += 1
                continue

            # Create the entry data
            clean_data = {
                CONF_HUB_IP: self._hub_ip,
                CONF_HUB_PORT: self._hub_port,
                CONF_DOOR_ID: door_id,
                CONF_DOOR_NAME: door_name,
            }

            # Create entry directly using async_init with SOURCE_IMPORT
            # This will call async_step_import which creates the entry
            await self.hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": config_entries.SOURCE_IMPORT},
                data=clean_data,
            )
            created_count += 1
            _LOGGER.info("Created entry for door: %s", door_name)

        # Return abort with success message
        _LOGGER.info("Door import complete: %d created, %d skipped", created_count, skipped_count)
        return self.async_abort(reason="doors_imported")

    async def async_step_manual(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle manual door configuration."""
        errors: dict[str, str] = {}

        if user_input is None:
            return self.async_show_form(step_id="manual", data_schema=self._user_schema())

        # Manual validation (avoid custom callables in Schema)
        hub_ip = (user_input.get(CONF_HUB_IP) or "").strip()
        hub_port = user_input.get(CONF_HUB_PORT)
        door_id = (user_input.get(CONF_DOOR_ID) or "").strip()
        door_name = (user_input.get(CONF_DOOR_NAME) or "").strip()

        if not _is_valid_ip_or_host(hub_ip):
            errors[CONF_HUB_IP] = "invalid_host"
        try:
            hub_port = int(hub_port)
            if hub_port < 1 or hub_port > 65535:
                errors[CONF_HUB_PORT] = "invalid_port"
        except (TypeError, ValueError):
            errors[CONF_HUB_PORT] = "invalid_port"

        if not door_id:
            errors[CONF_DOOR_ID] = "required"
        if not door_name:
            errors[CONF_DOOR_NAME] = "required"

        if errors:
            # Re-show form with the same values and error messages
            return self.async_show_form(
                step_id="manual",
                data_schema=self._user_schema(user_input),
                errors=errors,
            )

        # All good — create unique entry per hub:port:door
        unique_id = f"{hub_ip}:{hub_port}:{door_id}"
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()

        clean_data = {
            CONF_HUB_IP: hub_ip,
            CONF_HUB_PORT: hub_port,
            CONF_DOOR_ID: door_id,
            CONF_DOOR_NAME: door_name,
        }
        return self.async_create_entry(title=door_name, data=clean_data)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Optional reconfigure step (not commonly used by HA)."""
        return await self.async_step_user(user_input)

    async def async_step_import(self, import_config: dict[str, Any]) -> FlowResult:
        """Support import from auto-detection or YAML."""
        # Validate required fields
        hub_ip = import_config.get(CONF_HUB_IP, "").strip()
        hub_port = import_config.get(CONF_HUB_PORT, DEFAULT_PORT)
        door_id = import_config.get(CONF_DOOR_ID, "").strip()
        door_name = import_config.get(CONF_DOOR_NAME, "").strip()

        if not hub_ip or not door_id or not door_name:
            return self.async_abort(reason="invalid_import")

        # Create unique ID
        unique_id = f"{hub_ip}:{hub_port}:{door_id}"
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()

        # Create entry
        return self.async_create_entry(
            title=door_name,
            data={
                CONF_HUB_IP: hub_ip,
                CONF_HUB_PORT: hub_port,
                CONF_DOOR_ID: door_id,
                CONF_DOOR_NAME: door_name,
            },
        )

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return MySoftSystemsOptionsFlow(config_entry)


class MySoftSystemsOptionsFlow(config_entries.OptionsFlow):
    """Options (reconfigure) for an existing door/hub."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self.entry = entry

    def _schema(self, defaults: dict[str, Any]) -> vol.Schema:
        return vol.Schema(
            {
                vol.Required(CONF_HUB_IP, default=defaults.get(CONF_HUB_IP, "")): cv.string,
                vol.Required(CONF_HUB_PORT, default=defaults.get(CONF_HUB_PORT, DEFAULT_PORT)): int,
                vol.Required(CONF_DOOR_ID, default=defaults.get(CONF_DOOR_ID, "")): cv.string,
                vol.Required(CONF_DOOR_NAME, default=defaults.get(CONF_DOOR_NAME, self.entry.title)): cv.string,
            }
        )

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        cur = {**self.entry.data, **self.entry.options}

        if user_input is None:
            return self.async_show_form(step_id="init", data_schema=self._schema(cur))

        # Validate like in user step
        hub_ip = (user_input.get(CONF_HUB_IP) or "").strip()
        hub_port = user_input.get(CONF_HUB_PORT)
        door_id = (user_input.get(CONF_DOOR_ID) or "").strip()
        door_name = (user_input.get(CONF_DOOR_NAME) or "").strip()

        if not _is_valid_ip_or_host(hub_ip):
            errors[CONF_HUB_IP] = "invalid_host"
        try:
            hub_port = int(hub_port)
            if hub_port < 1 or hub_port > 65535:
                errors[CONF_HUB_PORT] = "invalid_port"
        except (TypeError, ValueError):
            errors[CONF_HUB_PORT] = "invalid_port"

        if not door_id:
            errors[CONF_DOOR_ID] = "required"
        if not door_name:
            errors[CONF_DOOR_NAME] = "required"

        if errors:
            return self.async_show_form(
                step_id="init",
                data_schema=self._schema(user_input),
                errors=errors,
            )

        # Update title if needed
        if door_name and door_name != self.entry.title:
            self.hass.config_entries.async_update_entry(self.entry, title=door_name)

        # Update unique_id if key fields changed
        new_uid = f"{hub_ip}:{hub_port}:{door_id}"
        if self.entry.unique_id != new_uid:
            self.hass.config_entries.async_update_entry(self.entry, unique_id=new_uid)

        # Store changes in options (setup code merges data+options)
        return self.async_create_entry(
            title="",
            data={
                CONF_HUB_IP: hub_ip,
                CONF_HUB_PORT: hub_port,
                CONF_DOOR_ID: door_id,
                CONF_DOOR_NAME: door_name,
            },
        )
