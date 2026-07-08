from datetime import datetime, time, timezone as dt_timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import requests


class MercadoLibreClient:
    def __init__(self, client_id, client_secret, base_url="https://api.mercadolibre.com", timeout=45, seller_id="", access_token="", local_timezone="America/Bogota"):
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = str(base_url or "https://api.mercadolibre.com").rstrip("/")
        self.timeout = timeout
        self.seller_id = str(seller_id or "").strip()
        self.provided_access_token = str(access_token or "").strip()
        self.local_timezone = ZoneInfo(str(local_timezone or "America/Bogota"))
        self.session = requests.Session()
        self._access_token = ""

    def authenticate(self):
        if self._access_token:
            return self._access_token
        if self.provided_access_token:
            self._access_token = self.provided_access_token
            self.session.headers.update({"Authorization": f"Bearer {self._access_token}"})
            if not self.seller_id:
                try:
                    payload = self.get_json("/users/me")
                    self.seller_id = str(payload.get("id") or "")
                except requests.HTTPError:
                    pass
            return self._access_token
        if not self.client_id or not self.client_secret:
            raise RuntimeError("Faltan MERCADOLIBRE_CLIENT_ID/MERCADOLIBRE_CLIENT_SECRET o MERCADOLIBRE_ACCESS_TOKEN.")
        response = self.session.post(
            f"{self.base_url}/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        self._access_token = payload["access_token"]
        self.session.headers.update({"Authorization": f"Bearer {self._access_token}"})
        if not self.seller_id:
            self.seller_id = str(payload.get("user_id") or "")
        return self._access_token

    def get_json(self, path, params=None):
        self.authenticate()
        response = self.session.get(f"{self.base_url}{path}", params=params or {}, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def day_bounds(self, target_date):
        start_local = datetime.combine(target_date, time.min, tzinfo=self.local_timezone)
        end_local = datetime.combine(target_date, time.max, tzinfo=self.local_timezone)
        return (
            start_local.astimezone(dt_timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            end_local.astimezone(dt_timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        )

    def iter_item_ids(self, status="active", limit=50, max_items=None):
        self.authenticate()
        if not self.seller_id:
            raise RuntimeError("Mercado Libre no devolvio seller_id en el token.")
        offset = 0
        fetched = 0
        while True:
            payload = self.get_json(
                f"/users/{self.seller_id}/items/search",
                params={"status": status, "limit": limit, "offset": offset},
            )
            item_ids = payload.get("results") or []
            if not item_ids:
                break
            for item_id in item_ids:
                yield item_id
                fetched += 1
                if max_items and fetched >= max_items:
                    return
            paging = payload.get("paging") or {}
            total = int(paging.get("total") or fetched)
            offset += len(item_ids)
            if offset >= total:
                break

    def get_items(self, item_ids, chunk_size=10):
        ids = list(item_ids)
        for start in range(0, len(ids), chunk_size):
            chunk = ids[start : start + chunk_size]
            payload = self.get_json("/items", params={"ids": ",".join(chunk)})
            for wrapper in payload:
                if int(wrapper.get("code") or 0) == 200 and wrapper.get("body"):
                    yield wrapper["body"]

    def iter_orders_for_day(self, target_date, limit=50):
        self.authenticate()
        if not self.seller_id:
            raise RuntimeError("Mercado Libre no devolvio seller_id en el token.")
        start, end = self.day_bounds(target_date)
        offset = 0
        while True:
            payload = self.get_json(
                "/orders/search",
                params={
                    "seller": self.seller_id,
                    "order.date_created.from": start,
                    "order.date_created.to": end,
                    "limit": limit,
                    "offset": offset,
                },
            )
            orders = payload.get("results") or []
            if not orders:
                break
            for order in orders:
                yield order
            paging = payload.get("paging") or {}
            total = int(paging.get("total") or offset + len(orders))
            offset += len(orders)
            if offset >= total:
                break


def decimal_from(value):
    return Decimal(str(value or "0"))
