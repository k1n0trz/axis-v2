from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import User, UserProfile


@receiver(post_save, sender=User)
def ensure_user_profile(sender, instance, created, **kwargs):
    if kwargs.get("raw"):
        return

    if created:
        UserProfile.objects.create(user=instance)
        return

    UserProfile.objects.get_or_create(user=instance)
