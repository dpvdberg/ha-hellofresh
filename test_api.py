"""
Standalone test script for the HelloFresh API client.
Run with: python test_api.py
Reads credentials from .credentials file (line 1: email, line 2: password)
or set environment variables HELLOFRESH_USERNAME and HELLOFRESH_PASSWORD.
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

# Import api.py directly without triggering the HA-dependent __init__.py
import importlib.util
spec = importlib.util.spec_from_file_location(
    "api", os.path.join(os.path.dirname(__file__), "custom_components", "hellofresh", "api.py")
)
api_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api_module)
HelloFreshAPI = api_module.HelloFreshAPI


async def main():
    # Try env vars first, then .credentials file
    username = os.environ.get("HELLOFRESH_USERNAME")
    password = os.environ.get("HELLOFRESH_PASSWORD")

    if not username or not password:
        creds_path = os.path.join(os.path.dirname(__file__), ".credentials")
        if os.path.exists(creds_path):
            with open(creds_path, "r") as f:
                lines = f.read().strip().splitlines()
                if len(lines) >= 2:
                    username = lines[0].strip()
                    password = lines[1].strip()

    if not username or not password:
        print("ERROR: No credentials found.")
        print("Either set HELLOFRESH_USERNAME/HELLOFRESH_PASSWORD env vars")
        print("or create a .credentials file with email on line 1, password on line 2.")
        return

    api = HelloFreshAPI(username, password)

    # Test login
    print("=" * 50)
    print("Testing login...")
    success = await api.async_validate_token()
    print(f"Login: {'OK' if success else 'FAILED'}")
    if not success:
        return

    # Test subscription fetch
    print("\n" + "=" * 50)
    print("Fetching subscription...")
    sub = await api.async_get_subscription()
    if sub:
        print(f"Subscription ID: {api._subscription_id}")
        print(f"Product SKU: {api._product_sku}")
        print(f"Next delivery week: {api.next_delivery_week}")
        print(f"Next modifiable week: {api.next_modifiable_week}")

        # Dump full subscription response
        os.makedirs("debug", exist_ok=True)
        with open("debug/test_subscription.json", "w", encoding="utf-8") as f:
            json.dump(sub, f, indent=2, ensure_ascii=False)
        print("Full subscription response dumped to debug/test_subscription.json")
    else:
        print("FAILED to fetch subscription")
        return

    # Fetch per-week delivery info (SKUs)
    print("\n" + "=" * 50)
    print("Fetching deliveries (per-week SKUs)...")
    await api.async_get_deliveries()
    print(f"Week SKUs: {api._week_skus}")

    # Test menus for upcoming weeks
    base_week = api.next_delivery_week
    os.makedirs("debug", exist_ok=True)

    for offset in range(-1, 4):
        week = api.week_offset(base_week, offset)
        sku = api._week_skus.get(week, api._product_sku)
        print("\n" + "=" * 50)
        print(f"Fetching menu for {week} (sku={sku})...")
        menu = await api.async_get_menu(week)
        if menu:
            preselected = menu.get("mealsPreselected")
            selected = [
                m for m in menu.get("meals", [])
                if m.get("selection", {}).get("quantity", 0) > 0
            ]
            print(f"Preselected: {preselected}, selected meals: {len(selected)}")
            for m in selected:
                recipe = m.get("recipe", {})
                print(f"  - {recipe.get('name')} ({recipe.get('prepTime')})")

            with open(f"debug/test_menu_{week}.json", "w", encoding="utf-8") as f:
                json.dump(menu, f, indent=2, ensure_ascii=False)
        else:
            print("FAILED to fetch menu")


if __name__ == "__main__":
    asyncio.run(main())
