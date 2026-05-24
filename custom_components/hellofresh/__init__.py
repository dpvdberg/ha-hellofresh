from pathlib import Path
import shutil

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall

from .const import DOMAIN
from .coordinator import HelloFreshCoordinator

PLATFORMS = ["sensor", "binary_sensor"]

CARD_FILENAME = "hellofresh-card.js"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = HelloFreshCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Copy the Lovelace card to www/ so it's served at /local/
    await hass.async_add_executor_job(_install_card, hass.config.path("www"))

    # Register refresh service (once for all entries)
    if not hass.services.has_service(DOMAIN, "refresh"):
        async def handle_refresh(call: ServiceCall) -> None:
            """Refresh all HelloFresh coordinators."""
            for coord in hass.data[DOMAIN].values():
                await coord.async_request_refresh()

        hass.services.async_register(DOMAIN, "refresh", handle_refresh)

    return True


def _install_card(www_dir: str) -> None:
    """Copy the card JS file to HA's www/community/hellofresh directory."""
    dest_dir = Path(www_dir) / "community" / "hellofresh"
    dest_dir.mkdir(parents=True, exist_ok=True)
    source = Path(__file__).parent / "www" / CARD_FILENAME
    dest = dest_dir / CARD_FILENAME
    if source.exists():
        shutil.copy2(source, dest)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
