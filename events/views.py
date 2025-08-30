from django.http import JsonResponse, QueryDict
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from .models import Event, EventImage, EventVideo,User
import os
import json
from django.contrib.auth import authenticate
from rest_framework.authtoken.models import Token
from django.views.decorators.csrf import csrf_protect
from django.contrib.auth import authenticate, login
from django.middleware.csrf import get_token
from django.contrib.auth import logout
from django.conf import settings



def add_images_to_event(event, images):
    """
    Add images to an event, up to a maximum of 5 images per event.
    """
    current_count = event.images.count()
    added = 0
    for image in images:
        if current_count < 5:
            EventImage.objects.create(event=event, image=image)
            current_count += 1
            added += 1
    return added

def get_event_images(event):
    """
    Return a list of dicts with id and url for all images of an event.
    """
    return [{'id': img.id, 'url': img.image.url} for img in event.images.all()]

def delete_event_image(event, image_id):
    """
    Delete a specific image from an event.
    """
    try:
        img = event.images.get(id=image_id)
        if img.image and os.path.isfile(img.image.path):
            os.remove(img.image.path)
        img.delete()
        return True, None
    except EventImage.DoesNotExist:
        return False, 'Image not found'

def add_or_replace_event_video(event, video_file):
    """
    Add or replace the video for an event.
    """
    event_video = getattr(event, 'video', None)
    if event_video:
        # Remove old file
        if event_video.video and os.path.isfile(event_video.video.path):
            os.remove(event_video.video.path)
        event_video.video = video_file
        event_video.save()
    else:
        EventVideo.objects.create(event=event, video=video_file)

def get_event_video(event):
    """
    Return a dict with id and url for the event's video, or None.
    """
    event_video = getattr(event, 'video', None)
    if event_video:
        return {'id': event_video.id, 'url': event_video.video.url}
    return None

def delete_event_video(event, video_id):
    """
    Delete the video for an event if it matches the given video_id.
    """
    try:
        event_video = event.video
        if event_video.id != video_id:
            return False, 'Video not found'
        if event_video.video and os.path.isfile(event_video.video.path):
            os.remove(event_video.video.path)
        event_video.delete()
        return True, None
    except EventVideo.DoesNotExist:
        return False, 'Video not found'

def delete_all_event_images(event):
    """
    Delete all images and their files for an event.
    """
    for img in event.images.all():
        if img.image and os.path.isfile(img.image.path):
            os.remove(img.image.path)
        img.delete()

def delete_event_video_file(event):
    """
    Delete the event's video and its file.
    """
    event_video = getattr(event, 'video', None)
    if event_video:
        if event_video.video and os.path.isfile(event_video.video.path):
            os.remove(event_video.video.path)
        event_video.delete()

# --- Views ---

@csrf_exempt
@require_http_methods(["GET", "POST"])
def event_list(request):
    if request.method == 'POST':
        # Accept JSON payload for event creation (no images/video in JSON)
        if request.content_type and request.content_type.startswith('application/json'):
            try:
                data = json.loads(request.body)
            except Exception:
                return JsonResponse({'error': 'Invalid JSON'}, status=400)
            name = data.get('name')
            description = data.get('description')
            date = data.get('date')
            event = Event.objects.create(name=name, description=description, date=date)
        else:
            # Handle multipart form data (for file uploads)
            name = request.POST.get('name')
            description = request.POST.get('description')
            date = request.POST.get('date')
            event = Event.objects.create(name=name, description=description, date=date)
            # Handle images (max 5)
            images = request.FILES.getlist('images')
            add_images_to_event(event, images)
            # Handle video (only one allowed)
            video = request.FILES.get('video')
            if video:
                add_or_replace_event_video(event, video)
        return JsonResponse({'status': 'success', 'event_id': event.id})
    else:  # GET
        events = Event.objects.all()
        events_data = []
        for event in events:
            images = get_event_images(event)
            video = get_event_video(event)
            events_data.append({
                'id': event.id,
                'name': event.name,
                'description': event.description,
                'date': str(event.date),
                'images': images,
                'video': video
            })
        return JsonResponse({'events': events_data})

@csrf_exempt
@require_http_methods(["PUT", "DELETE"])
def event_detail(request, event_id):
    try:
        event = Event.objects.get(id=event_id)
    except Event.DoesNotExist:
        return JsonResponse({'error': 'Event not found'}, status=404)

    if request.method == 'PUT':
        # Accept JSON payload for event editing (no images/video in JSON)
        if request.content_type and request.content_type.startswith('application/json'):
            try:
                data = json.loads(request.body)
            except Exception:
                return JsonResponse({'error': 'Invalid JSON'}, status=400)
            event.name = data.get('name', event.name)
            event.description = data.get('description', event.description)
            event.date = data.get('date', event.date)
            event.save()
        elif request.content_type.startswith('multipart'):
            data = request.POST
            files = request.FILES
            event.name = data.get('name', event.name)
            event.description = data.get('description', event.description)
            event.date = data.get('date', event.date)
            event.save()
            # Handle new images (append, up to 5)
            images = files.getlist('images')
            add_images_to_event(event, images)
            # Handle video (replace or create)
            video = files.get('video')
            if video:
                add_or_replace_event_video(event, video)
        else:
            # Fallback: try to parse as QueryDict (legacy)
            data = QueryDict(request.body)
            event.name = data.get('name', event.name)
            event.description = data.get('description', event.description)
            event.date = data.get('date', event.date)
            event.save()
        return JsonResponse({'status': 'success', 'event_id': event.id})

    elif request.method == 'DELETE':
        # Delete all images and video files, then the event
        delete_all_event_images(event)
        delete_event_video_file(event)
        event.delete()
        return JsonResponse({'status': 'success', 'message': 'Event deleted'})

@csrf_exempt
@require_http_methods(["GET", "POST", "PUT", "DELETE"])
def event_images(request, event_id, image_id=None):
    try:
        event = Event.objects.get(id=event_id)
    except Event.DoesNotExist:
        return JsonResponse({'error': 'Event not found'}, status=404)

    if request.method == 'GET':
        images = get_event_images(event)
        return JsonResponse({'images': images})

    elif request.method in ['POST', 'PUT']:
        images = request.FILES.getlist('images')
        added = add_images_to_event(event, images)
        return JsonResponse({'status': 'success', 'added': added, 'event_id': event.id})

    elif request.method == 'DELETE':
        success, error = delete_event_image(event, image_id)
        if success:
            return JsonResponse({'status': 'success', 'message': 'Image deleted'})
        else:
            return JsonResponse({'error': error}, status=404)

@csrf_exempt
@require_http_methods(["GET", "POST", "PUT", "DELETE"])
def event_videos(request, event_id, video_id=None):
    try:
        event = Event.objects.get(id=event_id)
    except Event.DoesNotExist:
        return JsonResponse({'error': 'Event not found'}, status=404)

    if request.method == 'GET':
        video = get_event_video(event)
        return JsonResponse({'video': video})

    elif request.method in ['POST', 'PUT']:
        video = request.FILES.get('video')
        if not video:
            return JsonResponse({'error': 'No video provided'}, status=400)
        add_or_replace_event_video(event, video)
        return JsonResponse({'status': 'success', 'event_id': event.id})

    elif request.method == 'DELETE':
        success, error = delete_event_video(event, video_id)
        if success:
            return JsonResponse({'status': 'success', 'message': 'Video deleted'})
        else:
            return JsonResponse({'error': error}, status=404)

@csrf_protect
def login_view(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            username = data.get("username")
            password = data.get("password")
        except Exception:
            return JsonResponse({"error": "Invalid request"}, status=400)
        user = authenticate(username=username, password=password)
        if user is not None and isinstance(user, User):
            login(request, user)  # Sets session cookie
            return JsonResponse({"success": True, "username": user.username})
        else:
            return JsonResponse({"error": "Invalid credentials"}, status=401)
    return JsonResponse({"error": "POST required"}, status=400)

def logout_view(request):
    if request.method == 'POST':
        logout(request)
        return JsonResponse({"status": "success"})
    return JsonResponse({"error": "Invalid request"}, status=400)

def ensure_csrf_cookie_view(request):
    if request.method == 'GET':
        return JsonResponse({"csrfToken": get_token(request)})
    return JsonResponse({"error": "Invalid request"}, status=400)

@csrf_exempt
def get_csrf_token_view(request):
    if request.method == 'GET':
        return JsonResponse({"csrfToken": get_token(request)})
    return JsonResponse({"error": "Invalid request"}, status=400)

@csrf_exempt
def check_user(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            user_name = data.get("user_name")
            email = data.get("email")
            
            if not user_name or not email:
                return JsonResponse({"error": "Username and email are required"}, status=400)
            
            # Check if user exists by username or email
            user = User.objects.filter(user_name=user_name, email=email).first()
            
            if user:
                return JsonResponse({
                    "exists": True,
                    "user": {
                        "user_name": user.user_name,
                        "email": user.email
                    }
                })
            else:
                return JsonResponse({"exists": False})
                
        except Exception as e:
            return JsonResponse({"error": "Invalid request"}, status=400)
    
    return JsonResponse({"error": "POST method required"}, status=405)

@csrf_exempt
def change_password(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        username = data.get("username")
        old_password = data.get("old_password")
        new_password = data.get("new_password")
        user = Admin.objects.filter(username=username).first()
        if user and user.check_password(old_password):
            user.set_password(new_password)
            user.save()
            Admin.objects.filter(username=user.username).update(password=new_password)
            return JsonResponse({"status": "success"})
        else:
            return JsonResponse({"error": "Invalid old password"}, status=401)
    return JsonResponse({"error": "Invalid request"}, status=400)
