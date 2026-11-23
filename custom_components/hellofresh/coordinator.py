from datetime import datetime, timedelta
import logging
import re

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import HelloFreshAPI
from .const import CONF_USERNAME, CONF_PASSWORD, DOMAIN, SCAN_INTERVAL_MINUTES

_LOGGER = logging.getLogger(__name__)

_ISO_DURATION = re.compile(r"^P(?:\d+D)?T?(?:(\d+)H)?(?:(\d+)M)?", re.IGNORECASE)


def iso_minutes(value: str | None) -> int | None:
    """Convert an ISO 8601 duration like 'PT1H5M' to minutes."""
    if not value:
        return None
    match = _ISO_DURATION.match(value)
    if not match or not any(match.groups()):
        return None
    hours, minutes = (int(g) if g else 0 for g in match.groups())
    return hours * 60 + minutes


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
        # The deliveries endpoint only lists the current and upcoming weeks. Once a week has been
        # delivered its box size (SKU) is no longer known, and asking the menu with the default SKU
        # returns a different selection. So remember SKUs and the last good data per week.
        self._cache = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
        self._cached: dict | None = None

    async def _async_update_data(self) -> dict:
        """Fetch data for current and upcoming weeks."""
        try:
            sub = await self.api.async_get_subscription()
            if not sub:
                raise UpdateFailed("Could not fetch subscription data")

            next_week = self.api.next_delivery_week
            modifiable_week = self.api.next_modifiable_week

            if self._cached is None:
                self._cached = await self._cache.async_load() or {}
            cached_skus: dict = self._cached.setdefault("week_skus", {})
            cached_weeks: dict = self._cached.setdefault("weeks", {})

            # Fetch per-week delivery info (includes correct SKU per week)
            await self.api.async_get_deliveries()
            known_skus = {**cached_skus, **self.api._week_skus}
            self.api._week_skus.update(known_skus)
            cached_skus.update(known_skus)

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

            # Fetch a window of weeks: one before next delivery + next 3
            weeks_data = {}
            if next_week:
                for offset in range(-1, 4):
                    week_str = self.api.week_offset(next_week, offset)
                    if week_str < next_week and (week_str in cached_weeks or week_str not in known_skus):
                        # Delivered week: keep what we saw before delivery. Asking HelloFresh again
                        # (possibly with an unknown box size) returns a different, wrong selection.
                        if week_str in cached_weeks:
                            weeks_data[week_str] = {**cached_weeks[week_str], "locked": True}
                        continue
                    menu = await self.api.async_get_menu(week_str)
                    if menu:
                        selected_meals = []
                        for meal in menu.get("meals", []):
                            selection = meal.get("selection")
                            if selection and selection.get("quantity", 0) > 0:
                                recipe = meal.get("recipe", {})
                                selected_meals.append({
                                    "id": recipe.get("id"),
                                    "quantity": selection.get("quantity", 1),
                                    "name": recipe.get("name"),
                                    "headline": recipe.get("headline"),
                                    "image": recipe.get("image"),
                                    "prep_time": recipe.get("prepTime"),
                                    "prep_minutes": iso_minutes(recipe.get("prepTime")),
                                    "total_minutes": iso_minutes(recipe.get("totalTime")),
                                    "cuisines": [c.get("name") for c in recipe.get("cuisines", []) if c.get("name")],
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

            # Remember the data per week, so a delivered week keeps showing what was in the box.
            cached_weeks.update(weeks_data)
            oldest = self.api.week_offset(next_week, -8) if next_week else ""
            for key in [k for k in cached_weeks if k < oldest]:
                cached_weeks.pop(key)
            for key in [k for k in cached_skus if k < oldest]:
                cached_skus.pop(key)
            await self._cache.async_save(self._cached)

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
