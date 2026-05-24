from datetime import datetime, timedelta
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

            # Extract delivery timing info from subscription
            delivery_weekday = sub.get("deliveryWeekday", 1)  # 1=Monday
            delivery_option = sub.get("deliveryOption", {})
            packing_day = delivery_option.get("packingDay", 7)  # 7=Sunday
            cutoff_days = int(delivery_option.get("cutoff", "-3 days").split()[0].replace("-", ""))

            # Calculate cutoff offset: days before delivery
            # packingDay is relative to deliveryDay (Sunday before Monday)
            # cutoff is relative to packing day
            # So total offset from delivery = (delivery - packing) + cutoff_days
            days_packing_to_delivery = (delivery_weekday - packing_day) % 7
            cutoff_offset_from_delivery = days_packing_to_delivery + cutoff_days

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

                        delivery_date = self._week_to_delivery_date(week_str, delivery_weekday)
                        cutoff_date = delivery_date - timedelta(days=cutoff_offset_from_delivery)

                        weeks_data[week_str] = {
                            "meals": selected_meals,
                            "meals_preselected": menu.get("mealsPreselected", False),
                            "locked": self._is_locked(week_str, modifiable_week),
                            "delivery_date": delivery_date.isoformat(),
                            "cutoff_date": cutoff_date.strftime("%Y-%m-%dT23:59:59"),
                        }

            # Determine next modifiable week's preselected status and cutoff
            modifiable_preselected = False
            modifiable_cutoff = None
            modifiable_delivery_date = None
            if modifiable_week and modifiable_week in weeks_data:
                modifiable_preselected = weeks_data[modifiable_week]["meals_preselected"]
                modifiable_cutoff = weeks_data[modifiable_week]["cutoff_date"]
                modifiable_delivery_date = weeks_data[modifiable_week]["delivery_date"]

            # Next delivery date (from subscription directly)
            next_delivery_str = sub.get("nextDelivery")
            next_delivery_date = None
            if next_delivery_str:
                next_delivery_date = next_delivery_str[:10]  # "2026-05-25"

            return {
                "next_delivery_week": next_week,
                "next_delivery_date": next_delivery_date,
                "next_modifiable_week": modifiable_week,
                "modification_deadline": modifiable_cutoff,
                "modifiable_delivery_date": modifiable_delivery_date,
                "meals_preselected": modifiable_preselected,
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

    @staticmethod
    def _week_to_delivery_date(week_str: str, delivery_weekday: int) -> datetime:
        """Convert ISO week string to the delivery date for that week."""
        year, w = week_str.split("-W")
        # ISO weekday: 1=Monday, 7=Sunday
        monday = datetime.strptime(f"{year}-W{int(w):02d}-1", "%G-W%V-%u")
        return monday + timedelta(days=delivery_weekday - 1)
