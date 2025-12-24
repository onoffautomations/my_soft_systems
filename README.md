# My Soft Systems Integration for Home Assistant

Home Assistant integration for **My Soft Systems** Mikvah door control system.

## Features

- 🚪 **Automatic Door Detection** - Connects to SQL Server database to auto-detect all doors
- 🎛️ **4 Control Buttons per Door** - Each door gets a device with 4 control buttons
- 🔧 **Manual Configuration** - Add doors manually if database access is not available
- 📱 **Device Grouping** - Each door appears as a separate device with all controls grouped
- ⚡ **Pure Python** - No compilation required, uses `python-tds` for SQL Server connectivity

## Control Buttons

Each door device includes 4 buttons:

1. **Open till next schedule** - Opens door until the next scheduled event
2. **Close Back to Schedule** - Closes door and returns to normal schedule
3. **Open for 1 Entry** - Opens door for a single entry only
4. **Close if open for 1 entry** - Closes door if it was opened for single entry

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the 3 dots in the top right corner
3. Select **Custom repositories**
4. Add repository URL: `https://github.com/onoffautomations/my_soft_systems`
5. Category: **Integration**
6. Click **ADD**
7. Click **INSTALL**
8. Restart Home Assistant


## Configuration

### Auto-Detect Mode (Recommended)

1. Go to **Settings** → **Devices & Services**
2. Click **+ ADD INTEGRATION**
3. Search for **My Soft Systems**
4. Select **Auto-detect from database**
5. Fill in the connection details:
   - **Hub IP/Hostname**: Your hub address (default: `mikvah-pc`)
   - **Hub Port**: Hub port number (default: `4960`)
   - **Database Host**: SQL Server host (default: `mikvah-pc`)
   - **Database Port**: SQL Server port (default: `1433`)
   - **Database Name**: Database name (default: `MyKehila`)
   - **Database Username**: SQL username
   - **Database Password**: Your SQL password
6. Select which doors to import:
   - ✅ Check **"Import all doors"** to import everything
   - Or uncheck it and select individual doors
7. Click **SUBMIT**

### Manual Mode

1. Go to **Settings** → **Devices & Services**
2. Click **+ ADD INTEGRATION**
3. Search for **My Soft Systems**
4. Select **Manual configuration**
5. Fill in the details:
   - **Hub IP/Hostname**: Your hub address (default: `mikvah-pc`)
   - **Hub Port**: Hub port number (default: `4960` or `4226`)
   - **Door ID**: The unique door identifier (from your system)
   - **Door Name**: A friendly name for the door
6. Click **SUBMIT**
7. Repeat for each door

## Database Requirements

For auto-detect to work, your SQL Server database must have a `Door` table with:

```sql
SELECT Oid AS DoorId, Description AS DoorName, OutputPort
FROM dbo.Door
ORDER BY Description;
```

The integration uses the `python-tds` library for pure Python SQL Server connectivity (no ODBC drivers required).

## Usage

After configuration, each door appears as a **device** in Home Assistant with 4 button entities:

```
📱 Front Door
   • button.front_door_open_till_next_schedule
   • button.front_door_close_back_to_schedule
   • button.front_door_open_for_1_entry
   • button.front_door_close_if_open_for_1_entry
```


## API Endpoints

The integration communicates with your My Soft Systems hub via HTTP:

```
http://{hub_ip}:{hub_port}/admin/Door/{door_id}/{param1}/{param2}
```

- **Open till next schedule**: `/admin/Door/{door_id}/true/false`
- **Close back to schedule**: `/admin/Door/{door_id}/true/true`
- **Open for 1 entry**: `/admin/Door/{door_id}/false/false`
- **Close if single open**: `/admin/Door/{door_id}/false/true`

## Troubleshooting

### Auto-detect not working

- Ensure SQL Server is accessible from Home Assistant
- Verify database credentials are correct
- Check that the `Door` table exists with the required columns
- Look at Home Assistant logs for connection errors

### Buttons not responding

- Verify hub IP and port are correct
- Check that the hub is accessible from Home Assistant
- Look at button entity attributes for `last_result` status
- Check Home Assistant logs for HTTP errors

### Devices not appearing

- Restart Home Assistant after installation
- Check **Settings** → **Devices & Services** → **My Soft Systems**
- Each door should show as a separate device
- If missing, try removing and re-adding the integration

## Development

### Project Structure

```
my_soft_systems/
├── __init__.py          # Integration setup
├── button.py           # Button entity implementation
├── config_flow.py      # Configuration flow (UI)
├── const.py           # Constants and defaults
├── manifest.json      # Integration metadata
└── strings.json       # UI translations
```

### Testing

```bash
# Copy to Home Assistant config
cp -r my_soft_systems /config/custom_components/

# Restart Home Assistant
ha core restart

# Check logs
ha core logs
```

## Credits

- **Developer**: OnOff Automations
- **System**: My Soft Systems Hub
- **Integration**: Custom Home Assistant component

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

- 🐛 **Issues**: [GitHub Issues](https://github.com/onoffautomations/my_soft_systems/issues)
- 💬 **Discussions**: [GitHub Discussions](https://github.com/onoffautomations/my_soft_systems/discussions)
- 📧 **Contact**: Create an issue for support

## Changelog

### v1.0.0 (2025-01-07)
- ✨ Initial release
- 🚪 Auto-detect doors from SQL Server database
- 🎛️ Manual door configuration
- 📱 Device creation with 4 control buttons per door
- ⚡ Pure Python SQL connectivity (python-tds)
- 🔧 Select all/deselect all door import toggle
