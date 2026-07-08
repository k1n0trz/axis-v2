import json

from django.core.management.base import BaseCommand
from django.conf import settings


def is_present(name):
    return bool(str(getattr(settings, name, "") or "").strip())


class Command(BaseCommand):
    help = "Valida que las variables de entorno de las integraciones de Helti esten completas."

    def handle(self, *args, **options):
        groups = {
            "onedrive": [
                "ONEDRIVE_CLIENT_ID",
                "ONEDRIVE_CLIENT_SECRET",
                "ONEDRIVE_TENANT_ID",
                "ONEDRIVE_USER_ID",
                "ONEDRIVE_SHARED_SALES_FILE_PATH",
            ],
            "woocommerce_co": [
                "WOOCOMMERCE_CO_BASE_URL",
                "WOOCOMMERCE_CO_CONSUMER_KEY",
                "WOOCOMMERCE_CO_CONSUMER_SECRET",
            ],
            "woocommerce_mx": [
                "WOOCOMMERCE_MX_BASE_URL",
                "WOOCOMMERCE_MX_CONSUMER_KEY",
                "WOOCOMMERCE_MX_CONSUMER_SECRET",
            ],
            "meta_ads": [
                "META_ACCESS_TOKEN",
                "META_CO_ACCOUNT_ID",
                "META_MX_ACCOUNT_ID",
                "META_EC_ACCOUNT_ID",
            ],
            "google_ads": [
                "GOOGLE_ADS_DEVELOPER_TOKEN",
                "GOOGLE_ADS_CLIENT_ID",
                "GOOGLE_ADS_CLIENT_SECRET",
                "GOOGLE_ADS_REFRESH_TOKEN",
            ],
            "shopify_bali": [
                "SHOPIFY_BALI_SHOP_DOMAIN",
                "SHOPIFY_BALI_ACCESS_TOKEN",
            ],
            "mercadolibre": [
                "MERCADOLIBRE_CLIENT_ID",
                "MERCADOLIBRE_CLIENT_SECRET",
            ],
            "exchange_rate": [
                "EXCHANGE_RATE_API_URL",
            ],
        }

        report = {"groups": {}, "ready_now": [], "blocked": []}
        for group_name, keys in groups.items():
            missing = [key for key in keys if not is_present(key)]
            ready = not missing
            report["groups"][group_name] = {
                "ready": ready,
                "present": {key: is_present(key) for key in keys},
                "missing": missing,
            }
            if ready:
                report["ready_now"].append(group_name)
            else:
                report["blocked"].append(group_name)

        report["next_best_execution_order"] = [
            "woocommerce_co",
            "woocommerce_mx",
            "onedrive",
            "meta_ads",
            "shopify_bali",
            "mercadolibre",
            "google_ads",
        ]
        report["notes"] = [
            "La validacion no expone secretos; solo confirma presencia o ausencia.",
            "Google Ads puede quedar pendiente sin bloquear el resto del roadmap.",
        ]
        self.stdout.write(json.dumps(report, indent=2))
