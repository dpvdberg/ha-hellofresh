from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HelloFreshCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: HelloFreshCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([HelloFreshPreselectedSensor(coordinator, entry)])


class HelloFreshPreselectedSensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor indicating if the next modifiable week has preselected meals."""

    _attr_has_entity_name = True
    _attr_name = "Meals Preselected"
    _attr_icon = "mdi:food-off"

    def __init__(self, coordinator: HelloFreshCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_meals_preselected"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="HelloFresh",
            manufacturer="HelloFresh",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def is_on(self) -> bool | None:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("meals_preselected", False)

    @property
    def extra_state_attributes(self) -> dict:
        if not self.coordinator.data:
            return {}
        return {
            "week": self.coordinator.data.get("next_modifiable_week"),
        }
