import time
from datetime import datetime, timedelta
import logging
from curl_cffi import requests as cffi_requests

_LOGGER = logging.getLogger(__name__)


class HelloFreshAPI:
    """Client for the HelloFresh API with automatic token refresh via curl_cffi."""

    def __init__(self, username: str, password: str) -> None:
        self._username = username
        self._password = password
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._token_expires_at: float = 0
        self._refresh_expires_at: float = 0
        self._base_url = "https://www.hellofresh.nl/gw/"
        self._login_url = "https://www.hellofresh.nl/gw/login"
        self._session: cffi_requests.Session | None = None
        self._subscription_id: str | None = None
        self._product_sku: str | None = None
        self._week_skus: dict[str, str] = {}
        self._next_delivery_week: str | None = None
        self._next_modifiable_week: str | None = None

    def _get_session(self) -> cffi_requests.Session:
        """Get or create a curl_cffi session with Chrome TLS fingerprint."""
        if self._session is None:
            self._session = cffi_requests.Session(impersonate="chrome")
        return self._session

    def _is_token_valid(self) -> bool:
        """Check if access token hasn't expired (with 5 min buffer)."""
        return self._access_token is not None and time.time() < (self._token_expires_at - 300)

    def _is_refresh_valid(self) -> bool:
        """Check if refresh token is still valid."""
        return self._refresh_token is not None and time.time() < self._refresh_expires_at

    def _login_headers(self) -> dict:
        return {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": "https://www.hellofresh.nl",
            "Referer": "https://www.hellofresh.nl/login",
        }

    async def async_login(self) -> bool:
        """Login with username/password to obtain tokens."""
        return await self._hass_async_run(self._do_login)

    async def _hass_async_run(self, func, *args):
        """Run blocking I/O in executor (HA pattern)."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, func, *args)

    def _do_login(self) -> bool:
        """Perform login (blocking)."""
        session = self._get_session()

        # Visit login page first to establish Cloudflare cookies
        try:
            session.get("https://www.hellofresh.nl/login")
        except Exception:
            pass

        payload = {"username": self._username, "password": self._password}
        try:
            resp = session.post(
                self._login_url,
                params={"country": "NL", "locale": "nl-NL"},
                json=payload,
                headers=self._login_headers(),
            )
        except Exception as err:
            _LOGGER.error("Login request error: %s", err)
            return False

        if resp.status_code != 200:
            _LOGGER.error("Login failed with status %s", resp.status_code)
            return False

        self._store_tokens(resp.json())
        _LOGGER.debug("Login successful, token expires in %s seconds",
                      resp.json().get("expires_in"))
        return True

    def _do_refresh(self) -> bool:
        """Refresh token (blocking)."""
        session = self._get_session()
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
            "username": self._username,
            "password": self._password,
        }
        try:
            resp = session.post(
                self._login_url,
                params={"country": "NL", "locale": "nl-NL"},
                json=payload,
                headers=self._login_headers(),
            )
        except Exception as err:
            _LOGGER.warning("Token refresh request error: %s", err)
            return False

        if resp.status_code != 200:
            _LOGGER.warning("Token refresh failed with status %s", resp.status_code)
            return False

        self._store_tokens(resp.json())
        _LOGGER.debug("Token refresh successful")
        return True

    def _store_tokens(self, data: dict) -> None:
        """Store tokens from login/refresh response."""
        self._access_token = data.get("access_token")
        self._refresh_token = data.get("refresh_token")
        issued_at = data.get("issued_at", time.time())
        expires_in = data.get("expires_in", 1800)
        refresh_expires_in = data.get("refresh_expires_in", 5184000)
        self._token_expires_at = issued_at + expires_in
        self._refresh_expires_at = issued_at + refresh_expires_in

    async def _ensure_token(self) -> None:
        """Ensure we have a valid token, refreshing or re-logging in as needed."""
        if self._is_token_valid():
            return

        # Try refresh first
        if self._is_refresh_valid():
            success = await self._hass_async_run(self._do_refresh)
            if success:
                return

        # Fall back to full login
        success = await self._hass_async_run(self._do_login)
        if not success:
            raise Exception("Failed to authenticate with HelloFresh")

    def _get_api_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Cache-Control": "no-cache, no-store",
            "Pragma": "no-cache",
            "Accept": "application/json",
        }

    async def async_get_subscription(self) -> dict | None:
        """Fetch subscription data and cache IDs."""
        await self._ensure_token()
        data = await self._hass_async_run(self._do_get_subscription)
        if data:
            items = data.get("items", [])
            if items:
                sub = items[0]
                self._subscription_id = sub.get("id")
                self._product_sku = sub.get("product", {}).get("sku")
                self._next_delivery_week = sub.get("nextDeliveryWeek")
                self._next_modifiable_week = sub.get("nextModifiableDeliveryWeek")

                return sub
        return None

    def _do_get_subscription(self) -> dict | None:
        session = self._get_session()
        resp = session.get(
            f"{self._base_url}api/customers/me/subscriptions",
            headers=self._get_api_headers(),
        )
        if resp.status_code != 200:
            _LOGGER.error("Subscription request failed: %s", resp.status_code)
            return None
        return resp.json()

    async def async_get_deliveries(self) -> None:
        """Fetch per-week delivery info to get the correct SKU per week."""
        await self._ensure_token()
        data = await self._hass_async_run(self._do_get_deliveries)
        if data:
            for item in data.get("items", []):
                week_id = item.get("id")
                product = item.get("product", {})
                sku = product.get("handle") or product.get("sku")
                if week_id and sku:
                    self._week_skus[week_id] = sku

    def _do_get_deliveries(self) -> dict | None:
        session = self._get_session()
        resp = session.get(
            f"{self._base_url}api/customers/me/deliveries",
            headers=self._get_api_headers(),
        )
        if resp.status_code != 200:
            _LOGGER.warning("Deliveries request failed: %s", resp.status_code)
            return None
        return resp.json()

    async def async_get_menu(self, week: str) -> dict | None:
        """Fetch the menu for a given week using the correct per-week SKU."""
        await self._ensure_token()
        if not self._subscription_id or not self._product_sku:
            await self.async_get_subscription()
        # Use per-week SKU from deliveries, fall back to subscription default
        sku = self._week_skus.get(week, self._product_sku)
        return await self._hass_async_run(self._do_get_menu, week, sku)

    def _do_get_menu(self, week: str, sku: str = None) -> dict | None:
        session = self._get_session()
        params = {
            "subscription": self._subscription_id,
            "product-sku": sku or self._product_sku,
            "week": week,
        }
        resp = session.get(
            f"{self._base_url}my-deliveries/menu",
            params=params,
            headers=self._get_api_headers(),
        )
        if resp.status_code != 200:
            _LOGGER.warning("Menu request for %s (sku=%s) failed: %s", week, sku, resp.status_code)
            return None
        return resp.json()

    async def async_validate_token(self) -> bool:
        """Validate credentials by attempting login."""
        return await self._hass_async_run(self._do_login)

    @property
    def next_delivery_week(self) -> str | None:
        return self._next_delivery_week

    @property
    def next_modifiable_week(self) -> str | None:
        return self._next_modifiable_week

    @staticmethod
    def week_offset(week_str: str, offset: int) -> str:
        """Calculate a week string offset by N weeks."""
        year, w = week_str.split("-W")
        date = datetime.strptime(f"{year}-W{int(w):02d}-1", "%G-W%V-%u")
        target = date + timedelta(weeks=offset)
        iso = target.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
