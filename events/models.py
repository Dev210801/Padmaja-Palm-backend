from django.db import models
from django.utils import timezone
from django.contrib.auth.hashers import make_password, check_password
import uuid
from datetime import timedelta
from django.contrib.auth.models import AbstractUser



# Create your models here.
class Event(models.Model):
    name = models.CharField(max_length=200, unique=True)
    description = models.TextField()
    date = models.DateField()

    def __str__(self):
        return self.name
def image_upload_to(instance, filename):
    return f'event_images/{instance.event.name}/{filename}'

class EventImage(models.Model):
    event = models.ForeignKey(Event, related_name='images', on_delete=models.CASCADE)
    image = models.ImageField(upload_to=image_upload_to)
    
def video_upload_to(instance, filename):
    return f'event_videos/{instance.event.name}/{filename}'
class EventVideo(models.Model):
    event = models.OneToOneField(Event, related_name='video', on_delete=models.CASCADE)
    video = models.FileField(upload_to=video_upload_to)

    def __str__(self):
        return f'Video for {self.event.name}'


class User(models.Model):
    user_name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=128)
    
    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        return check_password(raw_password, self.password)

    def __str__(self):
        return self.user_name