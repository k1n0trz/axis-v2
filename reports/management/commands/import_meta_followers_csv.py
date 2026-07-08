import json

from django.core.management.base import BaseCommand, CommandError

from reports.services.meta_followers_import import import_meta_followers_csv_file


class Command(BaseCommand):
    help = "Importa manualmente un CSV de Meta Ads Manager para Seguidores Awn Internacional."

    def add_arguments(self, parser):
        parser.add_argument("file_path", type=str)
        parser.add_argument("--country", default="")
        parser.add_argument("--target-currency", default="COP")

    def handle(self, *args, **options):
        try:
            result = import_meta_followers_csv_file(
                options["file_path"],
                country_code=options["country"],
                target_currency=options["target_currency"],
            )
        except FileNotFoundError as exc:
            raise CommandError(str(exc)) from exc
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
