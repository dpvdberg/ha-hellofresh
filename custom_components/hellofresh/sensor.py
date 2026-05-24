from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HelloFreshCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: HelloFreshCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([HelloFreshMenuSensor(coordinator, entry)])


class HelloFreshMenuSensor(CoordinatorEntity, SensorEntity):
    """Sensor that exposes all upcoming week menus as attributes."""

    _attr_has_entity_name = True
    _attr_name = "Upcoming Menus"
    _attr_icon = "mdi:food"

    def __init__(self, coordinator: HelloFreshCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_upcoming_menus"

    @property
    def native_value(self) -> str | None:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("next_delivery_week")

    @property
    def extra_state_attributes(self) -> dict:
        if not self.coordinator.data:
            return {}
        return {
            "next_delivery_week": self.coordinator.data.get("next_delivery_week"),
            "next_modifiable_week": self.coordinator.data.get("next_modifiable_week"),
            "weeks": self.coordinator.data.get("weeks", {}),
        }
