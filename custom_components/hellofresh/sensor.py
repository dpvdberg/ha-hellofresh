from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
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
    async_add_entities([
        HelloFreshMenuSensor(coordinator, entry),
        HelloFreshNextDeliverySensor(coordinator, entry),
        HelloFreshModificationDeadlineSensor(coordinator, entry),
    ])


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="HelloFresh",
        manufacturer="HelloFresh",
        entry_type=DeviceEntryType.SERVICE,
    )


class HelloFreshMenuSensor(CoordinatorEntity, SensorEntity):
    """Sensor that exposes all upcoming week menus as attributes."""

    _attr_has_entity_name = True
    _attr_name = "Upcoming Menus"
    _attr_icon = "mdi:food"

    def __init__(self, coordinator: HelloFreshCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_upcoming_menus"
        self._attr_device_info = _device_info(entry)

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


class HelloFreshNextDeliverySensor(CoordinatorEntity, SensorEntity):
    """Sensor showing the next delivery date."""

    _attr_has_entity_name = True
    _attr_name = "Next Delivery"
    _attr_icon = "mdi:truck-delivery"
    _attr_device_class = SensorDeviceClass.DATE

    def __init__(self, coordinator: HelloFreshCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_next_delivery"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self):
        if not self.coordinator.data:
            return None
        date_str = self.coordinator.data.get("next_delivery_date")
        if date_str:
            from datetime import date
            return date.fromisoformat(date_str)
        return None

    @property
    def extra_state_attributes(self) -> dict:
        if not self.coordinator.data:
            return {}
        return {
            "week": self.coordinator.data.get("next_delivery_week"),
        }


class HelloFreshModificationDeadlineSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing when modifications close for the next modifiable week."""

    _attr_has_entity_name = True
    _attr_name = "Modification Deadline"
    _attr_icon = "mdi:clock-alert"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: HelloFreshCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_modification_deadline"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self):
        if not self.coordinator.data:
            return None
        deadline_str = self.coordinator.data.get("modification_deadline")
        if deadline_str:
            from datetime import datetime, timezone
            return datetime.fromisoformat(deadline_str).replace(tzinfo=timezone.utc)
        return None

    @property
    def extra_state_attributes(self) -> dict:
        if not self.coordinator.data:
            return {}
        return {
            "week": self.coordinator.data.get("next_modifiable_week"),
            "delivery_date": self.coordinator.data.get("modifiable_delivery_date"),
        }
