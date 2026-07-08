from django import forms

import json
import os
import re
import struct

from django.utils import timezone

from django.contrib.auth.models import User

from .models import AdPlatform, BusinessUnit, Channel, Country, DailyAdSpend, DailyChannelSale, OperationalGoalTask, Product, UserProfile, WeeklyTask


VIEW_CHOICES = (("weekly", "Semana"), ("monthly", "Mes"), ("custom", "Personalizado"))
TIME_GRANULARITY_CHOICES = (("daily", "Diario"), ("weekly", "Semanal"), ("monthly", "Mensual"))
COMPARE_CHOICES = (("none", "Sin comparacion"), ("previous_period", "Periodo anterior"))
EXPORT_SCOPE_CHOICES = (("master", "Periodo completo"), ("metrics", "Metricas filtradas"), ("tasks", "Tareas filtradas"))
PROFILE_PHOTO_MAX_BYTES = 5 * 1024 * 1024
IMAGE_UPLOAD_EXTENSIONS = {".jpg", ".jpeg", ".png"}


class GlobalFilterForm(forms.Form):
    period_type = forms.ChoiceField(label="Periodo", choices=VIEW_CHOICES, required=False, initial="monthly", widget=forms.Select(attrs={"class": "form-select"}))
    date_start = forms.DateField(label="Fecha inicio", required=False, widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}))
    date_end = forms.DateField(label="Fecha fin", required=False, widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}))
    time_granularity = forms.ChoiceField(label="Vista", required=False, choices=TIME_GRANULARITY_CHOICES, initial="daily", widget=forms.Select(attrs={"class": "form-select"}))
    compare_mode = forms.ChoiceField(label="Comparacion", required=False, choices=COMPARE_CHOICES, initial="previous_period", widget=forms.Select(attrs={"class": "form-select"}))
    business_unit = forms.ChoiceField(label="Unidad", required=False, choices=(), widget=forms.Select(attrs={"class": "form-select"}))
    country = forms.ChoiceField(label="Pais", required=False, choices=(), widget=forms.Select(attrs={"class": "form-select"}))
    product = forms.ChoiceField(label="Producto", required=False, choices=(), widget=forms.Select(attrs={"class": "form-select"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["business_unit"].choices = [("", "Todas las unidades")] + [(item.slug, item.name) for item in BusinessUnit.objects.filter(is_active=True)]
        self.fields["country"].choices = [("", "Todos los paises")] + [(item.code, item.name) for item in Country.objects.filter(is_active=True)]
        self.fields["product"].choices = [("", "Todos los productos")] + [(item.slug, item.name) for item in Product.objects.filter(is_active=True).select_related("business_unit").order_by("business_unit__display_order", "display_order", "name")]

    def clean(self):
        cleaned_data = super().clean()
        date_start = cleaned_data.get("date_start")
        date_end = cleaned_data.get("date_end")
        if date_start and date_end and date_start > date_end:
            raise forms.ValidationError("La fecha inicio no puede ser posterior a la fecha fin.")
        return cleaned_data

    @property
    def axis_filter_meta_json(self):
        units = list(BusinessUnit.objects.filter(is_active=True).order_by("display_order", "name"))
        countries = list(Country.objects.filter(is_active=True).prefetch_related("business_units").order_by("display_order", "name"))
        products = list(Product.objects.filter(is_active=True).select_related("business_unit").order_by("business_unit__display_order", "display_order", "name"))

        meta = {
            "units": [unit.slug for unit in units],
            "countries": {},
            "products": {},
        }
        for unit in units:
            meta["countries"][unit.slug] = [country.code for country in countries if unit in list(country.business_units.all())]
            meta["products"][unit.slug] = [product.slug for product in products if product.business_unit_id == unit.id]
        return json.dumps(meta)


class WeeklyTaskFilterForm(GlobalFilterForm):
    area = forms.ChoiceField(
        label="Area",
        required=False,
        choices=(("", "Todas las areas"),) + tuple((choice, label) for choice, label in WeeklyTask.Area.choices),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    week_label = forms.CharField(label="Semana", required=False, widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Semana 13-19 Abr 2026"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["period_type"].initial = "weekly"


class MasterImportForm(forms.Form):
    excel_file = forms.FileField(label="Archivo Excel", widget=forms.ClearableFileInput(attrs={"class": "form-control", "accept": ".xlsx"}))

    def clean_excel_file(self):
        excel_file = self.cleaned_data["excel_file"]
        if not excel_file.name.lower().endswith(".xlsx"):
            raise forms.ValidationError("El archivo debe ser .xlsx")
        return excel_file


class ExportRequestForm(GlobalFilterForm):
    export_scope = forms.ChoiceField(label="Tipo de exportacion", choices=EXPORT_SCOPE_CHOICES, widget=forms.Select(attrs={"class": "form-select"}))


class MultiFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class AttachmentUploadForm(forms.Form):
    files = forms.FileField(
        label="Archivos",
        widget=MultiFileInput(attrs={"class": "form-control", "multiple": True, "accept": ".pdf,.ppt,.pptx,.png,.jpg,.jpeg,.xlsx,.xls,.doc,.docx"}),
    )
    business_unit = forms.ModelChoiceField(label="Unidad", queryset=BusinessUnit.objects.filter(is_active=True), required=False, widget=forms.Select(attrs={"class": "form-select"}))
    country = forms.ModelChoiceField(label="Pais", queryset=Country.objects.filter(is_active=True), required=False, widget=forms.Select(attrs={"class": "form-select"}))
    channel = forms.ModelChoiceField(label="Canal", queryset=Channel.objects.filter(is_active=True), required=False, widget=forms.Select(attrs={"class": "form-select"}))
    task = forms.ModelChoiceField(label="Tarea relacionada", queryset=WeeklyTask.objects.order_by("-date_start", "task_id"), required=False, widget=forms.Select(attrs={"class": "form-select"}))
    period_label = forms.CharField(label="Periodo", required=False, widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Semana 13-19 Abr 2026"}))
    description = forms.CharField(label="Descripcion", required=False, widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}))
    tags = forms.CharField(label="Etiquetas", required=False, widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "reporte, pauta, analisis"}))

    def clean_files(self):
        files = self.files.getlist("files")
        if not files:
            raise forms.ValidationError("Debes seleccionar al menos un archivo.")
        return files


def _png_dimensions(file_obj):
    signature = file_obj.read(24)
    if len(signature) < 24 or signature[:8] != b"\x89PNG\r\n\x1a\n":
        raise forms.ValidationError("El logo PNG no es valido.")
    return struct.unpack(">II", signature[16:24])


def _jpeg_dimensions(file_obj):
    data = file_obj.read(2)
    if data != b"\xff\xd8":
        raise forms.ValidationError("El logo JPG no es valido.")

    while True:
        marker_prefix = file_obj.read(1)
        if not marker_prefix:
            break
        if marker_prefix != b"\xff":
            continue

        marker = file_obj.read(1)
        while marker == b"\xff":
            marker = file_obj.read(1)
        if not marker:
            break

        if marker in {b"\xd8", b"\xd9"}:
            continue

        size_bytes = file_obj.read(2)
        if len(size_bytes) != 2:
            break
        segment_size = struct.unpack(">H", size_bytes)[0]
        if segment_size < 2:
            break

        if marker in {b"\xc0", b"\xc1", b"\xc2", b"\xc3", b"\xc5", b"\xc6", b"\xc7", b"\xc9", b"\xca", b"\xcb", b"\xcd", b"\xce", b"\xcf"}:
            file_obj.read(1)
            height, width = struct.unpack(">HH", file_obj.read(4))
            return width, height

        file_obj.seek(segment_size - 2, os.SEEK_CUR)

    raise forms.ValidationError("No fue posible leer las dimensiones del logo JPG.")


def _image_dimensions(uploaded_file):
    uploaded_file.seek(0)
    header = uploaded_file.read(24)
    uploaded_file.seek(0)
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        width, height = _png_dimensions(uploaded_file)
    elif header[:2] == b"\xff\xd8":
        width, height = _jpeg_dimensions(uploaded_file)
    else:
        raise forms.ValidationError("El logo debe estar en formato JPG o PNG.")
    uploaded_file.seek(0)
    return width, height


def _validate_jpg_png_upload(uploaded_file, label="La imagen", max_bytes=PROFILE_PHOTO_MAX_BYTES):
    if not uploaded_file or uploaded_file is False:
        return uploaded_file
    if not getattr(uploaded_file, "content_type", ""):
        return uploaded_file

    extension = os.path.splitext(uploaded_file.name)[1].lower()
    if extension not in IMAGE_UPLOAD_EXTENSIONS:
        raise forms.ValidationError(f"{label} debe estar en formato JPG o PNG.")
    if getattr(uploaded_file, "size", 0) > max_bytes:
        raise forms.ValidationError(f"{label} no puede superar 5 MB.")
    try:
        _image_dimensions(uploaded_file)
    except forms.ValidationError:
        raise forms.ValidationError(f"{label} debe ser un archivo JPG o PNG valido.")
    return uploaded_file


class BusinessUnitCreateForm(forms.ModelForm):
    assigned_channels = forms.ModelMultipleChoiceField(
        label="Canales asociados",
        queryset=Channel.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "form-select", "size": 8}),
    )

    class Meta:
        model = BusinessUnit
        fields = ("name", "description")
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "maxlength": 50, "placeholder": "Ej. Bali"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 4, "maxlength": 500, "placeholder": "Descripcion de la marca"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_channels"].queryset = Channel.objects.filter(is_active=True).order_by("name")

    def clean_description(self):
        description = self.cleaned_data.get("description", "").strip()
        if len(description) > 500:
            raise forms.ValidationError("La descripcion no puede superar los 500 caracteres.")
        return description

    def save(self, commit=True):
        business_unit = super().save(commit=commit)
        if commit:
            Channel.objects.filter(pk__in=self.cleaned_data.get("assigned_channels", [])).update(business_unit=business_unit)
        return business_unit


class ChannelCreateForm(forms.ModelForm):
    class Meta:
        model = Channel
        fields = ("name", "description", "business_unit", "logo")
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "maxlength": 80, "placeholder": "Ej. WhatsApp Colombia"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 4, "placeholder": "Descripcion del canal"}),
            "business_unit": forms.Select(attrs={"class": "form-select"}),
            "logo": forms.ClearableFileInput(attrs={"class": "form-control", "accept": ".jpg,.jpeg,.png,image/png,image/jpeg"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["business_unit"].label = "Marca"
        self.fields["business_unit"].required = False
        self.fields["business_unit"].queryset = BusinessUnit.objects.filter(is_active=True).order_by("display_order", "name")
        self.fields["logo"].help_text = "Solo JPG o PNG, maximo 500x500 px, formato cuadrado y fondo blanco."

    def clean_logo(self):
        logo = self.cleaned_data.get("logo")
        if not logo:
            return logo

        extension = os.path.splitext(logo.name)[1].lower()
        if extension not in {".jpg", ".jpeg", ".png"}:
            raise forms.ValidationError("El logo debe estar en formato JPG o PNG.")

        width, height = _image_dimensions(logo)
        if width != height:
            raise forms.ValidationError("El logo debe ser cuadrado.")
        if width > 500 or height > 500:
            raise forms.ValidationError("El logo no puede superar 500x500 px.")
        return logo


class DailyChannelSaleForm(forms.ModelForm):
    class Meta:
        model = DailyChannelSale
        fields = ("business_unit", "country", "channel", "sale_date", "sales_amount", "order_count", "notes")
        widgets = {
            "business_unit": forms.Select(attrs={"class": "form-select"}),
            "country": forms.Select(attrs={"class": "form-select"}),
            "channel": forms.Select(attrs={"class": "form-select"}),
            "sale_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "sales_amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "order_count": forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Observaciones opcionales"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["business_unit"].label = "Marca"
        self.fields["country"].label = "Pais"
        self.fields["channel"].label = "Canal"
        self.fields["business_unit"].queryset = BusinessUnit.objects.filter(is_active=True).order_by("display_order", "name")
        self.fields["country"].queryset = Country.objects.filter(is_active=True).order_by("display_order", "name")
        self.fields["channel"].queryset = Channel.objects.filter(is_active=True).order_by("display_order", "name")

    def clean_sale_date(self):
        sale_date = self.cleaned_data["sale_date"]
        if sale_date >= timezone.localdate():
            raise forms.ValidationError("Solo puedes registrar ventas hasta el dia anterior.")
        return sale_date


class DailyAdSpendForm(forms.ModelForm):
    class Meta:
        model = DailyAdSpend
        fields = ("business_unit", "country", "ad_platform", "spend_date", "spend_amount", "notes")
        widgets = {
            "business_unit": forms.Select(attrs={"class": "form-select"}),
            "country": forms.Select(attrs={"class": "form-select"}),
            "ad_platform": forms.Select(attrs={"class": "form-select"}),
            "spend_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "spend_amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Observaciones opcionales"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["business_unit"].label = "Marca"
        self.fields["country"].label = "Pais"
        self.fields["ad_platform"].label = "Fuente de pauta"
        self.fields["business_unit"].queryset = BusinessUnit.objects.filter(is_active=True).order_by("display_order", "name")
        self.fields["country"].queryset = Country.objects.filter(is_active=True).order_by("display_order", "name")
        self.fields["ad_platform"].queryset = AdPlatform.objects.filter(is_active=True).order_by("name")

    def clean_spend_date(self):
        spend_date = self.cleaned_data["spend_date"]
        if spend_date >= timezone.localdate():
            raise forms.ValidationError("Solo puedes registrar inversion hasta el dia anterior.")
        return spend_date


class ProfileForm(forms.ModelForm):
    first_name = forms.CharField(label="Nombre", max_length=150, required=False, widget=forms.TextInput(attrs={"class": "form-control"}))
    last_name = forms.CharField(label="Apellido", max_length=150, required=False, widget=forms.TextInput(attrs={"class": "form-control"}))
    email = forms.EmailField(label="Correo electronico", required=True, widget=forms.EmailInput(attrs={"class": "form-control"}))

    class Meta:
        model = UserProfile
        fields = ("phone_number", "photo")
        widgets = {
            "phone_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej. 3001234567"}),
            "photo": forms.ClearableFileInput(attrs={"class": "form-control", "accept": ".jpg,.jpeg,.png,image/png,image/jpeg"}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user")
        super().__init__(*args, **kwargs)
        self.fields["first_name"].initial = self.user.first_name
        self.fields["last_name"].initial = self.user.last_name
        self.fields["email"].initial = self.user.email

    def clean_photo(self):
        return _validate_jpg_png_upload(self.cleaned_data.get("photo"), label="La foto de perfil")

    def save(self, commit=True):
        profile = super().save(commit=False)
        self.user.first_name = self.cleaned_data.get("first_name", "")
        self.user.last_name = self.cleaned_data.get("last_name", "")
        self.user.email = self.cleaned_data.get("email", "")
        if commit:
            self.user.save(update_fields=["first_name", "last_name", "email"])
            profile.user = self.user
            profile.save()
        return profile


class MarketplaceDailyForm(forms.Form):
    sale_date = forms.DateField(
        label="Fecha",
        required=True,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )
    country = forms.ChoiceField(
        label="Pais",
        required=True,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    channel = forms.ChoiceField(
        label="Canal",
        required=True,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    sales_amount = forms.DecimalField(
        label="Ventas",
        required=True,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0", "placeholder": "Valor total de ventas"}),
    )
    spend_amount = forms.DecimalField(
        label="Gasto",
        required=True,
        initial=0,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0", "placeholder": "Inversion en publicidad"}),
    )
    order_count = forms.IntegerField(
        label="Ordenes",
        required=False,
        initial=0,
        widget=forms.NumberInput(attrs={"class": "form-control", "min": "0", "placeholder": "Numero de ordenes"}),
    )
    units = forms.IntegerField(
        label="Unidades",
        required=False,
        initial=0,
        widget=forms.NumberInput(attrs={"class": "form-control", "min": "0", "placeholder": "Unidades vendidas"}),
    )
    notes = forms.CharField(
        label="Notas",
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Observaciones (opcional)"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        marketplace_channels = Channel.objects.filter(
            is_active=True,
            business_unit__slug="marketplace"
        ).order_by("display_order", "name")
        marketplace_countries = Country.objects.filter(
            is_active=True,
            business_units__slug="marketplace",
        ).distinct().order_by("display_order", "name")
        self.fields["country"].choices = [(c.code, c.name) for c in marketplace_countries]
        self.fields["channel"].choices = [(c.slug, c.name) for c in marketplace_channels]
        self.fields["sale_date"].initial = timezone.localdate().isoformat()

    def clean(self):
        cleaned = super().clean()
        date = cleaned.get("sale_date")
        if date and date > timezone.localdate():
            raise forms.ValidationError("No puedes registrar ventas de fechas futuras.")
        return cleaned

    def save(self, user):
        from .models import BusinessUnit, Country, Channel, DailyChannelSale
        date = self.cleaned_data["sale_date"]
        country_code = self.cleaned_data["country"]
        channel_slug = self.cleaned_data["channel"]
        sales = self.cleaned_data["sales_amount"]
        spend = self.cleaned_data["spend_amount"]
        orders = self.cleaned_data.get("order_count") or 0
        units = self.cleaned_data.get("units") or 0
        notes = self.cleaned_data.get("notes", "")

        business_unit = BusinessUnit.objects.filter(slug="marketplace").first()
        country = Country.objects.filter(code=country_code, business_units__slug="marketplace").first()
        channel = Channel.objects.filter(slug=channel_slug).first()

        if not all([business_unit, country, channel]):
            return None

        sale, created = DailyChannelSale.objects.update_or_create(
            business_unit=business_unit,
            country=country,
            channel=channel,
            sale_date=date,
            defaults={
                "sales_amount": sales,
                "spend_amount": spend,
                "order_count": orders,
                "units": units,
                "source_type": "manual",
                "notes": notes,
            }
        )

        return sale


class OperationalGoalTaskUpdateForm(forms.ModelForm):
    class Meta:
        model = OperationalGoalTask
        fields = ("employee_response",)
        widgets = {
            "employee_response": forms.HiddenInput(),
        }

    def clean_employee_response(self):
        value = self.cleaned_data.get("employee_response", "").strip()
        value = re.sub(r"<\s*(script|style)[^>]*>.*?<\s*/\s*\1\s*>", "", value, flags=re.IGNORECASE | re.DOTALL)
        value = re.sub(r"\s+on\w+\s*=\s*(['\"]).*?\1", "", value, flags=re.IGNORECASE | re.DOTALL)
        value = re.sub(r"javascript\s*:", "", value, flags=re.IGNORECASE)
        return value

