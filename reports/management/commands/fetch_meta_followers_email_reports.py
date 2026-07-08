import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from reports.services.meta_followers_import import fetch_meta_followers_from_imap


class Command(BaseCommand):
    help = "Lee correos IMAP con reportes programados de Meta Ads Manager y los importa a Seguidores Awn Internacional."

    def add_arguments(self, parser):
        parser.add_argument("--host", default="")
        parser.add_argument("--port", type=int, default=0)
        parser.add_argument("--username", default="")
        parser.add_argument("--password", default="")
        parser.add_argument("--folder", default="")
        parser.add_argument("--subject-filter", default="")
        parser.add_argument("--from-filter", default="")
        parser.add_argument("--save-dir", default="")
        parser.add_argument("--all", action="store_true")
        parser.add_argument("--target-currency", default="COP")

    def handle(self, *args, **options):
        host = options["host"] or getattr(settings, "META_REPORTS_IMAP_HOST", "")
        port = options["port"] or getattr(settings, "META_REPORTS_IMAP_PORT", 993)
        username = options["username"] or getattr(settings, "META_REPORTS_IMAP_USERNAME", "")
        password = options["password"] or getattr(settings, "META_REPORTS_IMAP_PASSWORD", "")
        folder = options["folder"] or getattr(settings, "META_REPORTS_IMAP_FOLDER", "INBOX")
        subject_filter = options["subject_filter"] or getattr(settings, "META_REPORTS_IMAP_SUBJECT_FILTER", "")
        from_filter = options["from_filter"] or getattr(settings, "META_REPORTS_IMAP_FROM_FILTER", "")
        save_dir = options["save_dir"] or getattr(settings, "META_REPORTS_DOWNLOAD_DIR", "")

        if not host or not username or not password:
            raise CommandError("Falta configuracion IMAP de Meta reports en .env.")

        try:
            result = fetch_meta_followers_from_imap(
                host=host,
                port=port,
                username=username,
                password=password,
                folder=folder,
                subject_filter=subject_filter,
                from_filter=from_filter,
                save_dir=save_dir,
                unseen_only=not options["all"],
                target_currency=options["target_currency"],
            )
        except Exception as exc:
            raise CommandError(f"No fue posible importar reportes programados de Meta: {exc}") from exc

        self.stdout.write(
            json.dumps(
                {
                    "imported_reports": result["imported_reports"],
                    "count": len(result["imported_reports"]),
                    "diagnostics": result["diagnostics"],
                },
                indent=2,
                ensure_ascii=False,
                default=str,
            )
        )
