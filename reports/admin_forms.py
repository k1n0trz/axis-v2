from django import forms
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist

from .models import BusinessUnit, Channel, Country, JobTitle, Product, UserProfile


class ManagerChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        try:
            profile = obj.profile
        except ObjectDoesNotExist:
            profile = None
        role_name = profile.role.name if profile and profile.role else ""
        display_name = obj.get_full_name() or obj.username
        return f"{role_name} - {display_name}" if role_name else display_name


class UserProfileFieldsMixin(forms.ModelForm):
    first_name = forms.CharField(label="Nombre", max_length=150, required=False)
    last_name = forms.CharField(label="Apellido", max_length=150, required=False)
    email = forms.EmailField(label="Correo electronico", required=True)
    phone_number = forms.CharField(label="Numero de celular", max_length=30, required=False)
    role = forms.ModelChoiceField(label="Cargo", queryset=JobTitle.objects.none(), required=False)
    manager = ManagerChoiceField(label="Jefe", queryset=User.objects.none(), required=False)
    business_units = forms.ModelMultipleChoiceField(
        label="Marcas con acceso",
        queryset=BusinessUnit.objects.none(),
        required=False,
        widget=FilteredSelectMultiple("marcas", is_stacked=False),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].queryset = JobTitle.objects.filter(is_active=True).order_by("name")
        self.fields["manager"].queryset = (
            User.objects.filter(is_active=True, profile__role__isnull=False)
            .select_related("profile__role")
            .order_by("profile__role__name", "username")
            .distinct()
        )
        self.fields["business_units"].queryset = BusinessUnit.objects.filter(is_active=True).order_by("display_order", "name")
        profile = None
        if getattr(self, "instance", None) and self.instance.pk:
            try:
                profile = self.instance.profile
            except ObjectDoesNotExist:
                profile = None
        if profile and profile.pk:
            self.fields["phone_number"].initial = profile.phone_number
            self.fields["role"].initial = profile.role
            self.fields["manager"].initial = profile.manager
            self.fields["business_units"].initial = profile.business_units.all()
        if getattr(self, "instance", None) and self.instance.pk:
            self.fields["manager"].queryset = self.fields["manager"].queryset.exclude(pk=self.instance.pk)

    def _save_profile(self, user):
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.phone_number = self.cleaned_data.get("phone_number", "")
        profile.role = self.cleaned_data.get("role")
        profile.job_title = profile.role.name if profile.role else ""
        profile.manager = self.cleaned_data.get("manager")
        profile.save()
        profile.business_units.set(self.cleaned_data.get("business_units"))

    def clean_manager(self):
        manager = self.cleaned_data.get("manager")
        if getattr(self, "instance", None) and self.instance.pk and manager and manager.pk == self.instance.pk:
            raise forms.ValidationError("El usuario no puede asignarse a si mismo como jefe.")
        return manager

    def save(self, commit=True):
        return super().save(commit=commit)


class AxisUserCreationForm(UserProfileFieldsMixin, UserCreationForm):
    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("is_superuser"):
            cleaned_data["is_staff"] = True
            self.instance.is_staff = True
        return cleaned_data

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "first_name", "last_name", "email")


class AxisUserChangeForm(UserProfileFieldsMixin, UserChangeForm):
    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("is_superuser"):
            cleaned_data["is_staff"] = True
            self.instance.is_staff = True
        return cleaned_data

    class Meta(UserChangeForm.Meta):
        model = User
        fields = ("username", "first_name", "last_name", "email", "is_active", "is_staff", "is_superuser", "groups", "user_permissions")


class BusinessUnitAdminForm(forms.ModelForm):
    channels = forms.ModelMultipleChoiceField(
        label="Canales asignados",
        queryset=Channel.objects.none(),
        required=False,
        widget=FilteredSelectMultiple("canales", is_stacked=False),
    )
    countries = forms.ModelMultipleChoiceField(
        label="Paises asignados",
        queryset=Country.objects.none(),
        required=False,
        widget=FilteredSelectMultiple("paises", is_stacked=False),
    )
    products = forms.ModelMultipleChoiceField(
        label="Productos asignados",
        queryset=Product.objects.none(),
        required=False,
        widget=FilteredSelectMultiple("productos", is_stacked=False),
    )

    class Meta:
        model = BusinessUnit
        fields = ("name", "slug", "description", "display_order", "is_active")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["channels"].queryset = Channel.objects.order_by("name")
        self.fields["countries"].queryset = Country.objects.order_by("name")
        self.fields["products"].queryset = Product.objects.order_by("name")
        if self.instance.pk:
            self.fields["channels"].initial = self.instance.channels.all()
            self.fields["countries"].initial = self.instance.countries.all()
            self.fields["products"].initial = self.instance.products.all()

    def save(self, commit=True):
        business_unit = super().save(commit=commit)
        if commit:
            selected_channels = self.cleaned_data.get("channels")
            Channel.objects.filter(business_unit=business_unit).exclude(pk__in=selected_channels.values_list("pk", flat=True)).update(business_unit=None)
            selected_channels.update(business_unit=business_unit)
            selected_products = self.cleaned_data.get("products")
            Product.objects.filter(business_unit=business_unit).exclude(pk__in=selected_products.values_list("pk", flat=True)).update(business_unit=None)
            selected_products.update(business_unit=business_unit)
            business_unit.countries.set(self.cleaned_data.get("countries"))
        return business_unit
