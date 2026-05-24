from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import HelloFreshAPI
from .const import CONF_USERNAME, CONF_PASSWORD, SCAN_INTERVAL_MINUTES

_LOGGER = logging.getLogger(__name__)


class HelloFreshCoordinator(DataUpdateCoordinator):
    """Coordinator to fetch HelloFresh menu data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="HelloFresh",
            update_interval=timedelta(minutes=SCAN_INTERVAL_MINUTES),
        )
        self.api = HelloFreshAPI(entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD])

    async def _async_update_data(self) -> dict:
        """Fetch data for current and upcoming weeks."""
        try:
            sub = await self.api.async_get_subscription()
            if not sub:
                raise UpdateFailed("Could not fetch subscription data")

            next_week = self.api.next_delivery_week
            modifiable_week = self.api.next_modifiable_week

            # Fetch a window of weeks: current delivery + next 3
            weeks_data = {}
            if next_week:
                for offset in range(4):
                    week_str = self.api.week_offset(next_week, offset)
                    menu = await self.api.async_get_menu(week_str)
                    if menu:
                        selected_meals = []
                        for meal in menu.get("meals", []):
                            selection = meal.get("selection")
                            if selection and selection.get("quantity", 0) > 0:
                                recipe = meal.get("recipe", {})
                                selected_meals.append({
                                    "name": recipe.get("name"),
                                    "headline": recipe.get("headline"),
                                    "image": recipe.get("image"),
                                    "prep_time": recipe.get("prepTime"),
                                    "website_url": recipe.get("websiteURL"),
                                    "tags": [
                                        t.get("name")
                                        for t in recipe.get("tags", [])
                                        if t.get("displayLabel")
                                    ],
                                    "nutrition": recipe.get("nutrition"),
                                })

                        weeks_data[week_str] = {
                            "meals": selected_meals,
                            "meals_preselected": menu.get("mealsPreselected", False),
                            "locked": self._is_locked(week_str, modifiable_week),
                        }

            return {
                "next_delivery_week": next_week,
                "next_modifiable_week": modifiable_week,
                "weeks": weeks_data,
            }
        except Exception as err:
            raise UpdateFailed(f"Error fetching HelloFresh data: {err}") from err

    @staticmethod
    def _is_locked(week_str: str, modifiable_week: str | None) -> bool:
        """A week is locked if it's before the next modifiable week."""
        if not modifiable_week:
            return False
        return week_str < modifiable_week
