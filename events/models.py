from django.db import models
from django.utils import timezone
from django.contrib.auth.hashers import make_password, check_password
import uuid
from datetime import timedelta
from django.contrib.auth.models import AbstractUser
from django.utils.text import slugify
from cloudinary_storage.storage import VideoMediaCloudinaryStorage


# Create your models here.
class Event(models.Model):
    name = models.CharField(max_length=200, unique=True)
    description = models.TextField()
    date = models.DateField()

    def __str__(self):
        return self.name

def image_upload_to(instance, filename):
    # Store images under: <event-name-slug>/images/<filename>
    event_slug = slugify(instance.event.name)
    return f"{event_slug}/images/{filename}"

class EventImage(models.Model):
    event = models.ForeignKey(Event, related_name='images', on_delete=models.CASCADE)
    image = models.ImageField(upload_to=image_upload_to)
    is_profile = models.BooleanField(default=False)
    
def video_upload_to(instance, filename):
    # Store videos under: <event-name-slug>/videos/<filename>
    event_slug = slugify(instance.event.name)
    return f"{event_slug}/videos/{filename}"

class EventVideo(models.Model):
    event = models.OneToOneField(Event, related_name='video', on_delete=models.CASCADE)
    video = models.FileField(upload_to=video_upload_to, storage=VideoMediaCloudinaryStorage())

    def __str__(self):
        return f'Video for {self.event.name}'
