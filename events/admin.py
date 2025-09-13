from django.contrib import admin
from .models import Event, EventImage, EventVideo
# Register your models here.

admin.site.register(Event)
admin.site.register(EventImage)
admin.site.register(EventVideo)
