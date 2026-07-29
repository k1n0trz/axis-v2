from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import RoasTrafficLightSetting, User, UserProfile
from .templatetags.report_extras import ROAS_SETTING_CACHE_KEY, _roas_cache


@receiver(post_save, sender=RoasTrafficLightSetting)
@receiver(post_delete, sender=RoasTrafficLightSetting)
def clear_roas_setting_cache(sender, instance, **kwargs):
    # Solo limpia el proceso actual; el TTL de 60 s cubre a los demas workers.
    _roas_cache().delete(ROAS_SETTING_CACHE_KEY)


@receiver(post_save, sender=User)
def ensure_user_profile(sender, instance, created, **kwargs):
    if kwargs.get("raw"):
        return

    if created:
        UserProfile.objects.create(user=instance)
        return

    UserProfile.objects.get_or_create(user=instance)
