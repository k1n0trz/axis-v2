from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand

from reports.models import Attachment, BusinessUnit, Channel, Country, MetricRecord, Product, WeeklyTask


class Command(BaseCommand):
    help = "Carga catalogos y datos mock para reporting gerencial."

    def handle(self, *args, **options):
        business_units = {
            "uva": BusinessUnit.objects.update_or_create(slug="uva", defaults={"name": "Uva", "display_order": 1})[0],
            "bali": BusinessUnit.objects.update_or_create(slug="bali", defaults={"name": "Bali", "display_order": 2})[0],
            "marketplace": BusinessUnit.objects.update_or_create(slug="marketplace", defaults={"name": "Marketplace", "display_order": 3})[0],
        }

        countries = {}
        for index, (name, code) in enumerate([
            ("Colombia", "CO"),
            ("Ecuador", "EC"),
            ("Mexico", "MX"),
            ("Espana", "ES"),
            ("Panama", "PA"),
        ], start=1):
            countries[code] = Country.objects.update_or_create(code=code, defaults={"name": name, "display_order": index})[0]

        channel_specs = [
            ("Ecommerce", "ecommerce-uva", "uva"),
            ("WhatsApp Colombia", "whatsapp-uva-co", "uva"),
            ("WhatsApp Ecuador", "whatsapp-uva-ec", "uva"),
            ("Amazon", "amazon", "uva"),
            ("Sellerchat", "sellerchat", "uva"),
            ("Web", "bali-web", "bali"),
            ("WhatsApp", "bali-whatsapp", "bali"),
            ("Tienda Fisica", "bali-tienda-fisica", "bali"),
            ("Mercado Libre", "mercado-libre", "marketplace"),
            ("Falabella", "falabella", "marketplace"),
            ("Rappi", "rappi", "marketplace"),
            ("Farmatodo", "farmatodo", "marketplace"),
        ]
        channels = {}
        for index, (name, slug, unit_key) in enumerate(channel_specs, start=1):
            channel = (
                Channel.objects.filter(business_unit=business_units[unit_key], slug=slug).first()
                or Channel.objects.filter(business_unit=business_units[unit_key], name=name).first()
            )
            if channel:
                channel.name = name
                channel.slug = slug
                channel.display_order = index
                channel.save(update_fields=["name", "slug", "display_order", "updated_at"])
            else:
                channel = Channel.objects.create(
                    business_unit=business_units[unit_key],
                    slug=slug,
                    name=name,
                    display_order=index,
                )
            channels[slug] = channel

        product_specs = [
            "Copa Menstrual",
            "Disco Menstrual",
            "Panties Menstruales",
            "Kits",
            "Lubricantes",
            "Cubrepezones",
            "Dilatadores",
        ]
        products = {}
        for index, name in enumerate(product_specs, start=1):
            products[name] = Product.objects.update_or_create(
                name=name,
                business_unit=business_units["uva"],
                defaults={"display_order": index},
            )[0]

        week_start = date(2026, 4, 13)
        week_end = date(2026, 4, 19)
        month_start = date(2026, 4, 1)
        month_end = date(2026, 4, 30)

        metric_rows = [
            ("M-001", "uva", "CO", "ecommerce-uva", "Copa Menstrual", "Meta Ads", "weekly", "Semana 13-19 Abr 2026", week_start, week_end, "sales_total", Decimal("18500000")),
            ("M-002", "uva", "CO", "ecommerce-uva", "Copa Menstrual", "Meta Ads", "weekly", "Semana 13-19 Abr 2026", week_start, week_end, "investment", Decimal("4200000")),
            ("M-003", "uva", "CO", "ecommerce-uva", "Copa Menstrual", "Meta Ads", "weekly", "Semana 13-19 Abr 2026", week_start, week_end, "cpa_by_product", Decimal("25610")),
            ("M-004", "uva", "CO", "ecommerce-uva", "Copa Menstrual", "Meta Ads", "weekly", "Semana 13-19 Abr 2026", week_start, week_end, "messages", Decimal("820")),
            ("M-005", "uva", "CO", "ecommerce-uva", "Copa Menstrual", "Meta Ads", "weekly", "Semana 13-19 Abr 2026", week_start, week_end, "purchases", Decimal("164")),
            ("M-006", "uva", "CO", "ecommerce-uva", "Copa Menstrual", "Meta Ads", "weekly", "Semana 13-19 Abr 2026", week_start, week_end, "conversion_rate", Decimal("0.20")),
            ("M-007", "uva", "CO", "ecommerce-uva", "Copa Menstrual", "Meta Ads", "weekly", "Semana 13-19 Abr 2026", week_start, week_end, "investment_by_product", Decimal("4200000")),
            ("M-008", "uva", "CO", "ecommerce-uva", "Copa Menstrual", "Meta Ads", "weekly", "Semana 13-19 Abr 2026", week_start, week_end, "ad_spend_by_country", Decimal("4200000")),
            ("M-009", "uva", "CO", "ecommerce-uva", "Copa Menstrual", "Meta Ads", "monthly", "Abril 2026", month_start, month_end, "sales_month", Decimal("71200000")),
            ("M-010", "uva", "CO", "whatsapp-uva-co", "Kits", "WhatsApp Campaigns", "weekly", "Semana 13-19 Abr 2026", week_start, week_end, "sales_whatsapp", Decimal("9800000")),
            ("M-011", "uva", "CO", "whatsapp-uva-co", "Kits", "WhatsApp Campaigns", "weekly", "Semana 13-19 Abr 2026", week_start, week_end, "messages", Decimal("1240")),
            ("M-012", "uva", "CO", "whatsapp-uva-co", "Kits", "WhatsApp Campaigns", "weekly", "Semana 13-19 Abr 2026", week_start, week_end, "cpl_by_campaign", Decimal("6325")),
            ("M-013", "uva", "EC", "whatsapp-uva-ec", "Kits", "WhatsApp Campaigns", "monthly", "Abril 2026", month_start, month_end, "cpl_monthly", Decimal("6880")),
            ("M-014", "uva", "ES", "amazon", "Panties Menstruales", "TikTok Ads", "monthly", "Abril 2026", month_start, month_end, "sales_month", Decimal("12200000")),
            ("M-015", "uva", "ES", "amazon", "Panties Menstruales", "TikTok Ads", "monthly", "Abril 2026", month_start, month_end, "investment_by_product", Decimal("3100000")),
            ("M-016", "uva", "CO", "ecommerce-uva", "Copa Menstrual", "Comfama Uva", "weekly", "Semana 13-19 Abr 2026", week_start, week_end, "sales_total", Decimal("3600000")),
            ("M-017", "uva", "CO", "ecommerce-uva", "Copa Menstrual", "Comfama Uva", "weekly", "Semana 13-19 Abr 2026", week_start, week_end, "messages", Decimal("140")),
            ("M-018", "uva", "CO", "ecommerce-uva", "Copa Menstrual", "Comfama Uva", "weekly", "Semana 13-19 Abr 2026", week_start, week_end, "investment", Decimal("900000")),
            ("M-019", "uva", "CO", "ecommerce-uva", "Disco Menstrual", "Comfama Uva", "monthly", "Abril 2026", month_start, month_end, "sales_month", Decimal("2100000")),
            ("M-020", "uva", "CO", "ecommerce-uva", "Panties Menstruales", "Comfama Uva", "monthly", "Abril 2026", month_start, month_end, "sales_month", Decimal("2800000")),
            ("M-021", "bali", "", "bali-web", "", "Google Ads", "weekly", "Semana 13-19 Abr 2026", week_start, week_end, "sales_web", Decimal("26400000")),
            ("M-022", "bali", "", "bali-web", "", "Google Ads", "weekly", "Semana 13-19 Abr 2026", week_start, week_end, "ad_spend", Decimal("6600000")),
            ("M-023", "bali", "", "bali-web", "", "Google Ads", "weekly", "Semana 13-19 Abr 2026", week_start, week_end, "orders", Decimal("410")),
            ("M-024", "bali", "", "bali-web", "", "Google Ads", "weekly", "Semana 13-19 Abr 2026", week_start, week_end, "average_ticket", Decimal("64390")),
            ("M-025", "bali", "", "bali-whatsapp", "", "WhatsApp Campaigns", "weekly", "Semana 13-19 Abr 2026", week_start, week_end, "sales_whatsapp", Decimal("11800000")),
            ("M-026", "bali", "", "bali-whatsapp", "", "WhatsApp Campaigns", "weekly", "Semana 13-19 Abr 2026", week_start, week_end, "messages", Decimal("1520")),
            ("M-027", "bali", "", "bali-whatsapp", "", "WhatsApp Campaigns", "weekly", "Semana 13-19 Abr 2026", week_start, week_end, "closed_deals", Decimal("216")),
            ("M-028", "bali", "", "bali-whatsapp", "", "WhatsApp Campaigns", "weekly", "Semana 13-19 Abr 2026", week_start, week_end, "close_rate", Decimal("0.14")),
            ("M-029", "bali", "", "bali-web", "", "Google Ads", "monthly", "Abril 2026", month_start, month_end, "sales_month", Decimal("98400000")),
            ("M-030", "marketplace", "CO", "mercado-libre", "", "Mercado Libre Ads", "weekly", "Semana 13-19 Abr 2026", week_start, week_end, "sales_marketplace", Decimal("17500000")),
            ("M-031", "marketplace", "CO", "mercado-libre", "", "Mercado Libre Ads", "weekly", "Semana 13-19 Abr 2026", week_start, week_end, "ad_spend", Decimal("3500000")),
            ("M-032", "marketplace", "CO", "mercado-libre", "", "Mercado Libre Ads", "weekly", "Semana 13-19 Abr 2026", week_start, week_end, "orders", Decimal("312")),
            ("M-033", "marketplace", "CO", "mercado-libre", "", "Mercado Libre Ads", "weekly", "Semana 13-19 Abr 2026", week_start, week_end, "units", Decimal("459")),
            ("M-034", "marketplace", "CO", "mercado-libre", "", "Mercado Libre Ads", "weekly", "Semana 13-19 Abr 2026", week_start, week_end, "conversion_rate", Decimal("0.11")),
            ("M-035", "marketplace", "CO", "falabella", "", "Falabella Ads", "weekly", "Semana 13-19 Abr 2026", week_start, week_end, "sales_marketplace", Decimal("8200000")),
            ("M-036", "marketplace", "CO", "falabella", "", "Falabella Ads", "weekly", "Semana 13-19 Abr 2026", week_start, week_end, "ad_spend", Decimal("1200000")),
            ("M-037", "marketplace", "EC", "rappi", "", "Rappi Ads", "weekly", "Semana 13-19 Abr 2026", week_start, week_end, "sales_marketplace", Decimal("6400000")),
            ("M-038", "marketplace", "EC", "rappi", "", "Rappi Ads", "weekly", "Semana 13-19 Abr 2026", week_start, week_end, "ad_spend", Decimal("680000")),
            ("M-039", "marketplace", "CO", "farmatodo", "", "WhatsApp Campaigns", "weekly", "Semana 13-19 Abr 2026", week_start, week_end, "sales_marketplace", Decimal("4800000")),
            ("M-040", "marketplace", "CO", "farmatodo", "", "WhatsApp Campaigns", "weekly", "Semana 13-19 Abr 2026", week_start, week_end, "conversion_rate", Decimal("0.09")),
            ("M-041", "marketplace", "CO", "mercado-libre", "", "Mercado Libre Ads", "monthly", "Abril 2026", month_start, month_end, "sales_month", Decimal("68200000")),
            ("M-042", "marketplace", "CO", "mercado-libre", "", "Mercado Libre Ads", "monthly", "Abril 2026", month_start, month_end, "operational_profit", Decimal("9100000")),
        ]

        created_metrics = {}
        for record_id, unit_key, country_code, channel_slug, product_name, campaign_type, period_type, label, date_start, date_end, metric_name, metric_value in metric_rows:
            metric, _ = MetricRecord.objects.update_or_create(
                record_id=record_id,
                defaults={
                    "business_unit": business_units[unit_key],
                    "country": countries.get(country_code),
                    "channel": channels.get(channel_slug),
                    "product": products.get(product_name),
                    "subchannel": "",
                    "campaign_type": campaign_type,
                    "source": "seed_data",
                    "period_type": period_type,
                    "period_label": label,
                    "date_start": date_start,
                    "date_end": date_end,
                    "metric_name": metric_name,
                    "metric_value": metric_value,
                    "currency": "COP",
                    "value_origin": MetricRecord.ValueOrigin.IMPORTED,
                    "notes": "Dato mock inicial",
                },
            )
            created_metrics[record_id] = metric

        task_rows = [
            ("T-001", "Semana 13-19 Abr 2026", week_start, week_end, "Ecommerce", "uva", "CO", "ecommerce-uva", "Optimizar checkout para Copa Menstrual en Colombia", "completed", "high", "optimizacion", "conversion", "Checkout actualizado", "Impacto directo en conversion web", "M-001", "ATT-001"),
            ("T-002", "Semana 13-19 Abr 2026", week_start, week_end, "Pauta", "uva", "CO", "whatsapp-uva-co", "Reasignar presupuesto hacia WhatsApp Colombia", "completed", "critical", "estrategica", "rentabilidad", "CPL semanal mejorado", "Ajuste de pauta con foco en mensajes", "M-012", "ATT-002"),
            ("T-003", "Semana 13-19 Abr 2026", week_start, week_end, "Pauta", "uva", "CO", "ecommerce-uva", "Consolidar bloque Comfama Uva por producto cardinal", "in_progress", "high", "preventiva", "ventas", "Tablero parcial disponible", "Pendiente cierre del mes", "M-016", "ATT-003"),
            ("T-004", "Semana 13-19 Abr 2026", week_start, week_end, "Chat Web Bali", "bali", "", "bali-whatsapp", "Depurar script de seguimiento de cierres", "in_progress", "high", "correctiva", "conversion", "Pendiente validacion final", "Seguimiento con equipo comercial", "M-028", "ATT-004"),
            ("T-005", "Semana 13-19 Abr 2026", week_start, week_end, "Tecnico", "bali", "", "bali-web", "Auditar pixel y eventos de Shopify", "completed", "medium", "preventiva", "tecnologia", "Eventos validados", "Soporte a medicion de conversion", "M-022", "ATT-005"),
            ("T-006", "Semana 13-19 Abr 2026", week_start, week_end, "Marketplace", "marketplace", "CO", "mercado-libre", "Actualizar pricing y catalogo en Mercado Libre", "completed", "high", "optimizacion", "ventas", "Publicaciones ajustadas", "Mejora de competitividad", "M-030", "ATT-006"),
            ("T-007", "Semana 13-19 Abr 2026", week_start, week_end, "Operativo", "marketplace", "CO", "falabella", "Resolver incidencias de catalogo en Falabella", "blocked", "critical", "incidencia", "operacion", "Pendiente respuesta del canal", "Afecta disponibilidad de catalogo", "M-035", "ATT-007"),
            ("T-008", "Semana 13-19 Abr 2026", week_start, week_end, "Pauta", "bali", "", "bali-web", "Optimizar CPA en Google Ads Bali Web", "in_progress", "high", "optimizacion", "rentabilidad", "Se redujo CPC", "Seguimiento diario", "M-022", "ATT-008"),
        ]

        created_tasks = {}
        for task_id, week_label, date_start, date_end, area, unit_key, country_code, channel_slug, task_name, status, priority, task_type, impact, result, notes, related_metric, attachment_ref in task_rows:
            task, _ = WeeklyTask.objects.update_or_create(
                task_id=task_id,
                defaults={
                    "week_label": week_label,
                    "date_start": date_start,
                    "date_end": date_end,
                    "area": area,
                    "business_unit": business_units[unit_key],
                    "country": countries.get(country_code),
                    "channel": channels.get(channel_slug),
                    "task_name": task_name,
                    "status": status,
                    "priority": priority,
                    "task_type": task_type,
                    "impact": impact,
                    "result": result,
                    "notes": notes,
                    "related_metric": created_metrics.get(related_metric),
                    "attachment_ref": attachment_ref,
                },
            )
            created_tasks[task_id] = task

        attachment_rows = [
            ("ATT-001", "uva", "CO", "ecommerce-uva", "Semana 13-19 Abr 2026", "T-001", "checkout-colombia.pdf", "pdf", "https://example.com/checkout-colombia.pdf", "Optimizacion checkout", "checkout, ecommerce", "Soporte de optimizacion checkout"),
            ("ATT-002", "uva", "CO", "whatsapp-uva-co", "Semana 13-19 Abr 2026", "T-002", "redistribucion-whatsapp.xlsx", "excel", "https://example.com/redistribucion-whatsapp.xlsx", "Reasignacion de presupuesto", "whatsapp, pauta", "Reasignacion de presupuesto"),
            ("ATT-003", "uva", "CO", "ecommerce-uva", "Semana 13-19 Abr 2026", "T-003", "comfama-uva.png", "image", "https://example.com/comfama-uva.png", "Vista previa de Comfama", "comfama, uva", "Vista previa de Comfama por producto"),
            ("ATT-004", "bali", "", "bali-whatsapp", "Semana 13-19 Abr 2026", "T-004", "bali-whatsapp-script.png", "image", "https://example.com/bali-whatsapp-script.png", "Hallazgo de seguimiento", "bali, whatsapp", "Hallazgo de seguimiento"),
        ]

        for attachment_ref, unit_key, country_code, channel_slug, period_label, task_id, file_name, file_type, path, description, tags, comment in attachment_rows:
            Attachment.objects.update_or_create(
                attachment_ref=attachment_ref,
                defaults={
                    "business_unit": business_units[unit_key],
                    "country": countries.get(country_code),
                    "channel": channels.get(channel_slug),
                    "period_label": period_label,
                    "task": created_tasks.get(task_id),
                    "file_name": file_name,
                    "file_type": file_type,
                    "file_path_or_url": path,
                    "description": description,
                    "tags": tags,
                    "comment": comment,
                },
            )

        self.stdout.write(self.style.SUCCESS("Catalogos y datos mock cargados correctamente."))
