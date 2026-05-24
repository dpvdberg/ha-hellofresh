import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .api import HelloFreshAPI
from .const import DOMAIN, CONF_USERNAME, CONF_PASSWORD


class HelloFreshConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for HelloFresh."""

    VERSION = 1

    async def async_step_user(self, user_input=None) -> FlowResult:
        errors = {}

        if user_input is not None:
            api = HelloFreshAPI(
                user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
            )
            valid = await api.async_validate_token()

            if valid:
                await self.async_set_unique_id(
                    f"hellofresh_{user_input[CONF_USERNAME]}"
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="HelloFresh",
                    data=user_input,
                )
            else:
                errors["base"] = "invalid_auth"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )
