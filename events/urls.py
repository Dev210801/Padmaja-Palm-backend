from django.urls import path
from .views import *
from django.conf import settings
from django.conf.urls.static import static

# events/urls.py (refactored)
from django.urls import path
from .views import *

urlpatterns = [
    path('', event_list, name='event_list'),
    path('<int:event_id>/', event_detail, name='event_detail'),
    path('images/<int:event_id>/', event_images, name='event_images_list'),
    path('images/<int:event_id>/<int:image_id>/', event_images, name='event_images_detail'),
    path('videos/<int:event_id>/', event_videos, name='event_videos_list'),
    path('videos/<int:event_id>/<int:video_id>/', event_videos, name='event_videos_detail'),
    path('login/', login_view, name='admin_login'),
    path('logout/', logout_view, name='admin_logout'),
    path('get-csrf-token/', get_csrf_token_view, name='get_csrf_token'),
    path('check-user/', check_user, name='check_user'),
    path('change-password/', change_password, name='change_password'),
    path('storage/analytics/', storage_analytics, name='storage_analytics'),
    # Admin-only signed downloads
    path('download/image/<int:event_id>/<int:image_id>/', download_event_image, name='download_event_image'),
    path('download/video/<int:event_id>/<int:video_id>/', download_event_video, name='download_event_video'),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)