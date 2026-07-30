import csv
import email
import imaplib
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from email.header import decode_header
from email.utils import parsedate_to_datetime
from io import StringIO
from pathlib import Path

from django.conf import settings

from reports.integrations.clients import ExchangeRateClient
from reports.models import AwnInternationalFollowerMetric, Country
from reports.services.sales_dashboard import ensure_uva_catalogs, parse_excel_date
from reports.utils.numbers import parse_decimal


COUNTRY_ALIASES = {
    "ecuador": "EC",
    "mexico": "MX",
    "méxico": "MX",
    "mx": "MX",
    "ec": "EC",
}


def normalize_text(value):
    raw = unicodedata.normalize("NFKD", str(value or "").strip().lower())
    return "".join(char for char in raw if not unicodedata.combining(char))


def decode_bytes(blob):
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return blob.decode(encoding)
        except UnicodeDecodeError:
            continue
    return blob.decode("utf-8", errors="replace")


def decode_mime_text(value):
    parts = decode_header(value or "")
    chunks = []
    for payload, encoding in parts:
        if isinstance(payload, bytes):
            chunks.append(payload.decode(encoding or "utf-8", errors="replace"))
        else:
            chunks.append(payload)
    return "".join(chunks)


def infer_country_code(filename="", fallback=""):
    normalized = normalize_text(filename)
    for token, code in COUNTRY_ALIASES.items():
        if token in normalized:
            return code
    return (fallback or "").upper()


@dataclass
class FollowersImportResult:
    imported_rows: int
    created: int
    updated: int
    skipped: int
    country_code: str
    metric_dates: list[str]
    source_files: list[str]

    def to_dict(self):
        return {
            "imported_rows": self.imported_rows,
            "created": self.created,
            "updated": self.updated,
            "skipped": self.skipped,
            "country_code": self.country_code,
            "metric_dates": self.metric_dates,
            "source_files": self.source_files,
        }


def _spend_header_and_currency(headers):
    for header in headers:
        normalized = normalize_text(header)
        if normalized.startswith("importe gastado"):
            if "(" in header and ")" in header:
                return header, header.split("(", 1)[1].split(")", 1)[0].strip().upper()
            return header, "COP"
    return None, "COP"


def _required_headers(headers):
    normalized = {normalize_text(item): item for item in headers}
    return {
        "report_start": normalized.get("inicio del informe"),
        "report_end": normalized.get("fin del informe"),
        "adset_name": normalized.get("nombre del conjunto de anuncios"),
        "results": normalized.get("resultados"),
        "result_indicator": normalized.get("indicador de resultado"),
        "profile_visits": normalized.get("visitas al perfil de instagram"),
        "followers": normalized.get("seguidores de instagram"),
    }


def _build_fx_client():
    fx_url = getattr(settings, "EXCHANGE_RATE_API_URL", "")
    fx_key = getattr(settings, "EXCHANGE_RATE_API_KEY", "")
    if not fx_url:
        return None
    return ExchangeRateClient(fx_url, api_key=fx_key)


def import_meta_followers_csv_bytes(file_bytes, source_name, country_code="", target_currency="COP"):
    ensure_uva_catalogs()
    text = decode_bytes(file_bytes)
    reader = csv.DictReader(StringIO(text))
    headers = reader.fieldnames or []
    required = _required_headers(headers)
    missing = [key for key, value in required.items() if not value]
    if missing:
        raise ValueError(
            "El CSV de Meta no trae las columnas necesarias para followers: "
            + ", ".join(missing)
        )

    spend_header, spend_currency = _spend_header_and_currency(headers)
    if not spend_header:
        raise ValueError("El CSV de Meta no trae columna de importe gastado.")

    inferred_country = infer_country_code(source_name, fallback=country_code)
    if inferred_country not in {"EC", "MX"}:
        raise ValueError(
            "No fue posible inferir el pais del reporte. Usa nombre de archivo con Ecuador/Mexico o pasa el pais explicitamente."
        )

    country = Country.objects.filter(code=inferred_country).first()
    if not country:
        raise ValueError(f"No existe el pais {inferred_country} en Helti.")

    fx_client = _build_fx_client()
    totals = {}
    skipped = 0
    matched_rows = 0
    source_files = {source_name}

    for row in reader:
        indicator = normalize_text(row.get(required["result_indicator"]))
        if indicator != "profile_visit_view":
            skipped += 1
            continue
        metric_date = parse_excel_date(row.get(required["report_start"])) or parse_excel_date(row.get(required["report_end"]))
        if not metric_date:
            skipped += 1
            continue
        results = parse_decimal(row.get(required["results"]))
        profile_visits = parse_decimal(row.get(required["profile_visits"]))
        followers = parse_decimal(row.get(required["followers"]))
        spend = parse_decimal(row.get(spend_header))
        if spend_currency != target_currency:
            if not fx_client:
                raise ValueError("Se requiere configuracion de divisas para convertir importes de followers a COP.")
            spend = fx_client.convert(spend_currency, target_currency, spend, target_date=metric_date)
        bucket = totals.setdefault(
            metric_date,
            {
                "visits": Decimal("0"),
                "followers": Decimal("0"),
                "spend": Decimal("0"),
                "adsets": [],
            },
        )
        bucket["visits"] += results or profile_visits
        bucket["followers"] += followers
        bucket["spend"] += spend
        if row.get(required["adset_name"]):
            bucket["adsets"].append(str(row.get(required["adset_name"])).strip())
        matched_rows += 1

    created = 0
    updated = 0
    dates = []
    for metric_date, values in sorted(totals.items()):
        visits_int = int(values["visits"])
        followers_int = int(values["followers"])
        spend_amount = values["spend"]
        cpr = (spend_amount / values["visits"]) if values["visits"] else Decimal("0")
        cps = (spend_amount / values["followers"]) if values["followers"] else Decimal("0")
        _, was_created = AwnInternationalFollowerMetric.objects.update_or_create(
            country=country,
            metric_date=metric_date,
            defaults={
                "instagram_profile_visits": visits_int,
                "new_followers": followers_int,
                "spend_amount": spend_amount,
                "cpr": cpr,
                "cps": cps,
                "source_type": AwnInternationalFollowerMetric.SourceType.IMPORTED,
                "source_file": source_name,
                "source_row": 0,
                "notes": "Importado automaticamente desde reporte programado de Meta Ads Manager. "
                + "Adsets incluidos: "
                + ", ".join(values["adsets"][:8]),
            },
        )
        created += int(was_created)
        updated += int(not was_created)
        dates.append(metric_date.isoformat())

    return FollowersImportResult(
        imported_rows=matched_rows,
        created=created,
        updated=updated,
        skipped=skipped,
        country_code=inferred_country,
        metric_dates=dates,
        source_files=sorted(source_files),
    )


def import_meta_followers_csv_file(file_path, country_code="", target_currency="COP"):
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"No existe el archivo: {path}")
    return import_meta_followers_csv_bytes(path.read_bytes(), path.name, country_code=country_code, target_currency=target_currency)


def _search_query(subject_filter="", from_filter="", unseen_only=True):
    clauses = ["UNSEEN"] if unseen_only else ["ALL"]
    if subject_filter:
        clauses.extend(["SUBJECT", f'"{subject_filter}"'])
    if from_filter:
        clauses.extend(["FROM", f'"{from_filter}"'])
    return " ".join(clauses)


def fetch_meta_followers_from_imap(
    host,
    port,
    username,
    password,
    folder="INBOX",
    subject_filter="",
    from_filter="",
    save_dir="",
    unseen_only=True,
    target_currency="COP",
):
    save_root = Path(save_dir) if save_dir else None
    if save_root:
        save_root.mkdir(parents=True, exist_ok=True)

    imported = []
    diagnostics = {
        "folder": folder,
        "subject_filter": subject_filter,
        "from_filter": from_filter,
        "unseen_only": unseen_only,
        "matched_messages": 0,
    }
    with imaplib.IMAP4_SSL(host, port) as client:
        client.login(username, password)
        client.select(folder)
        status, data = client.search(None, _search_query(subject_filter, from_filter, unseen_only))
        if status != "OK":
            raise RuntimeError("No fue posible consultar correos IMAP para reportes de Meta.")
        message_ids = [item for item in data[0].split() if item]
        diagnostics["matched_messages"] = len(message_ids)
        for message_id in message_ids:
            status, payload = client.fetch(message_id, "(RFC822)")
            if status != "OK" or not payload or not payload[0]:
                continue
            raw_email = payload[0][1]
            message = email.message_from_bytes(raw_email)
            mail_subject = decode_mime_text(message.get("Subject", ""))
            sent_at = parsedate_to_datetime(message.get("Date")) if message.get("Date") else None
            for part in message.walk():
                disposition = str(part.get("Content-Disposition") or "")
                if "attachment" not in disposition.lower():
                    continue
                filename = decode_mime_text(part.get_filename() or "")
                if not filename.lower().endswith(".csv"):
                    continue
                attachment_bytes = part.get_payload(decode=True) or b""
                source_name = filename
                if save_root:
                    safe_name = filename
                    if sent_at:
                        safe_name = f"{sent_at.date().isoformat()}-{filename}"
                    file_path = save_root / safe_name
                    file_path.write_bytes(attachment_bytes)
                    source_name = file_path.name
                result = import_meta_followers_csv_bytes(
                    attachment_bytes,
                    source_name=source_name,
                    target_currency=target_currency,
                )
                imported.append(
                    {
                        "subject": mail_subject,
                        "attachment": source_name,
                        "result": result.to_dict(),
                    }
                )
            if imported:
                client.store(message_id, "+FLAGS", "\\Seen")
    return {
        "imported_reports": imported,
        "diagnostics": diagnostics,
    }
