from django.http import JsonResponse, QueryDict
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from .models import Event, EventImage, EventVideo
import os
import json
from django.contrib.auth import authenticate
from rest_framework.authtoken.models import Token
from django.views.decorators.csrf import csrf_protect
from django.contrib.auth import authenticate, login
from django.middleware.csrf import get_token
from django.contrib.auth import logout
from django.conf import settings
from django.utils.text import slugify
import os
import logging
logger = logging.getLogger(__name__)
try:
    import cloudinary
    from cloudinary import utils as cld_utils
    from cloudinary import api as cld_api
except Exception:
    cloudinary = None
    cld_utils = None
    cld_api = None


def add_images_to_event(event, images):
    """
    Add images to an event, up to a maximum of 5 images per event.
    """
    current_count = event.images.count()
    to_add = len(images)
    max_allowed = 5
    if current_count + to_add > max_allowed:
        remaining = max_allowed - current_count
        raise ValueError(f"You can upload up to {max_allowed} images per event. Currently you have {current_count}. You can add {max(remaining, 0)} more.")
    added = 0
    for image in images:
        # Server-side size check: 10 MB per image
        try:
            size_bytes = getattr(image, 'size', None)
            if isinstance(size_bytes, int) and size_bytes > 10 * 1024 * 1024:
                raise ValueError(f"Image file too large. Got {size_bytes}. Maximum is {10 * 1024 * 1024}.")
        except Exception:
            pass
        created = EventImage.objects.create(event=event, image=image)
        # If this is the first image overall, auto-mark as profile
        if current_count == 0 and added == 0:
            created.is_profile = True
            created.save(update_fields=["is_profile"])
        added += 1
    return added

def get_event_images(event):
    """
    Return a list of dicts with id and url for all images of an event.
    """
    return [{'id': img.id, 'url': img.image.url, 'is_profile': getattr(img, 'is_profile', False)} for img in event.images.all()]

def delete_event_image(event, image_id):
    """
    Delete a specific image from an event.
    """
    try:
        img = event.images.get(id=image_id)
    except EventImage.DoesNotExist:
        return False, 'Image not found'
    # Do not allow deleting the last remaining image
    if event.images.count() <= 1:
        return False, 'Cannot delete the last image. An event must have at least one image.'
    is_profile = getattr(img, 'is_profile', False)
    # Delete file and DB row
    if img.image:
        img.image.delete(save=False)
    img.delete()
    # If the deleted image was the profile, set another image as profile
    if is_profile:
        first_other = event.images.first()
        if first_other and not getattr(first_other, 'is_profile', False):
            first_other.is_profile = True
            first_other.save(update_fields=["is_profile"])
    return True, None

def set_profile_image(event, image_id):
    """
    Set a specific image as the profile image for an event.
    """
    try:
        img = event.images.get(id=image_id)
    except EventImage.DoesNotExist:
        return False, 'Image not found'
    # Unmark current profile image
    for i in event.images.all():
        if getattr(i, 'is_profile', False):
            i.is_profile = False
            i.save(update_fields=["is_profile"])
    # Mark new image as profile
    img.is_profile = True
    img.save(update_fields=["is_profile"])
    return True, None

def add_or_replace_event_video(event, video_file):
    """
    Add or replace the video for an event.
    """
    event_video = getattr(event, 'video', None)
    if event_video:
        # Enforce max 1 video: require delete before uploading new one
        raise ValueError("This event already has a video. Please delete it before uploading a new one.")
    else:
        # Server-side size check: 100 MB per video
        try:
            size_bytes = getattr(video_file, 'size', None)
            if isinstance(size_bytes, int) and size_bytes > 100 * 1024 * 1024:
                raise ValueError(f"Video file too large. Got {size_bytes}. Maximum is {100 * 1024 * 1024}.")
        except Exception:
            pass
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
        if event_video.video:
            event_video.video.delete(save=False)
        event_video.delete()
        return True, None
    except EventVideo.DoesNotExist:
        return False, 'Video not found'

def delete_all_event_images(event):
    """
    Delete all images and their files for an event.
    """
    for img in event.images.all():
        if img.image:
            img.image.delete(save=False)
        img.delete()

def delete_event_video_file(event):
    """
    Delete the event's video and its file.
    """
    event_video = getattr(event, 'video', None)
    if event_video:
        if event_video.video:
            event_video.video.delete(save=False)
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
            return JsonResponse({'status': 'success', 'event_id': event.id})
        else:
            # Handle multipart form data (for file uploads)
            name = request.POST.get('name')
            description = request.POST.get('description')
            date = request.POST.get('date')
            images = request.FILES.getlist('images')
            if not images:
                return JsonResponse({'error': 'At least one image is required to create an event.'}, status=400)
            event = Event.objects.create(name=name, description=description, date=date)
            # Handle images (max 5)
            try:
                add_images_to_event(event, images)
            except Exception as e:
                return JsonResponse({'error': str(e)}, status=400)
            # Handle video (only one allowed)
            video = request.FILES.get('video')
            if video:
                try:
                    add_or_replace_event_video(event, video)
                except Exception as e:
                    return JsonResponse({'error': str(e)}, status=400)
        return JsonResponse({'status': 'success', 'event_id': event.id})
    else:  # GET
        # Server-side pagination with latest-first ordering
        try:
            page = int(request.GET.get('page', '1'))
            page_size = int(request.GET.get('page_size', '6'))
        except ValueError:
            page, page_size = 1, 6

        queryset = Event.objects.all().order_by('-date', '-id')
        total = queryset.count()

        start = max((page - 1), 0) * max(page_size, 1)
        end = start + max(page_size, 1)
        page_items = queryset[start:end]

        events_data = []
        for event in page_items:
            images = get_event_images(event)
            video = get_event_video(event)
            profile = None
            for im in images:
                if im.get('is_profile'):
                    profile = im
                    break
            if not profile and images:
                profile = images[0]
            events_data.append({
                'id': event.id,
                'name': event.name,
                'description': event.description,
                'date': event.date.isoformat() if event.date else None,
                'images': images,
                'profile_image': profile,
                'video': video
            })
        return JsonResponse({
            'events': events_data,
            'count': total,
            'page': page,
            'page_size': page_size,
        })

@csrf_exempt
@require_http_methods(["GET", "PUT", "DELETE"])
def event_detail(request, event_id):
    try:
        event = Event.objects.get(id=event_id)
    except Event.DoesNotExist:
        return JsonResponse({'error': 'Event not found'}, status=404)
        
    if request.method == 'GET':
        # Return event details including images and video
        images = get_event_images(event)
        profile = None
        for im in images:
            if im.get('is_profile'):
                profile = im
                break
        if not profile and images:
            profile = images[0]
        event_data = {
            'id': event.id,
            'name': event.name,
            'description': event.description,
            'date': event.date.isoformat() if event.date else None,
            'images': images,
            'profile_image': profile,
            'video': get_event_video(event)
        }
        return JsonResponse(event_data)

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
            try:
                add_images_to_event(event, images)
            except Exception as e:
                return JsonResponse({'error': str(e)}, status=400)
            # Handle video (replace or create)
            video = files.get('video')
            if video:
                try:
                    add_or_replace_event_video(event, video)
                except Exception as e:
                    return JsonResponse({'error': str(e)}, status=400)
        else:
            # Fallback: try to parse as QueryDict (legacy)
            data = QueryDict(request.body)
            event.name = data.get('name', event.name)
            event.description = data.get('description', event.description)
            event.date = data.get('date', event.date)
            event.save()
        return JsonResponse({'status': 'success', 'event_id': event.id})

    elif request.method == 'DELETE':
        # Delete all images and video files, and purge from Cloudinary by prefix, then delete the event
        delete_all_event_images(event)
        delete_event_video_file(event)
        try:
            if cld_api is not None:
                ev_slug = slugify(event.name)
                prefix = f"media/{ev_slug}/"
                # Delete all resources under prefix for both images and videos
                try:
                    cld_api.delete_resources_by_prefix(prefix, resource_type='image', type='upload')
                except Exception:
                    pass
                try:
                    cld_api.delete_resources_by_prefix(prefix, resource_type='video', type='upload')
                except Exception:
                    pass
                # Attempt to delete subfolders and root folder (best-effort)
                for folder in [f"media/{ev_slug}/images", f"media/{ev_slug}/videos", f"media/{ev_slug}"]:
                    try:
                        cld_api.delete_folder(folder)
                    except Exception:
                        pass
        except Exception:
            # Best-effort cleanup; ignore errors
            pass
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
        # Support setting profile flag via JSON PUT to a specific image
        if request.method == 'PUT' and image_id and request.content_type and request.content_type.startswith('application/json'):
            try:
                data = json.loads(request.body or '{}')
            except Exception:
                data = {}
            if data.get('is_profile') is True:
                # Unset existing
                try:
                    img = event.images.get(id=image_id)
                except EventImage.DoesNotExist:
                    return JsonResponse({'error': 'Image not found'}, status=404)
                event.images.exclude(id=img.id).update(is_profile=False)
                img.is_profile = True
                img.save(update_fields=["is_profile"])
                return JsonResponse({'status': 'success', 'event_id': event.id})
            return JsonResponse({'error': 'No valid fields to update'}, status=400)
        # Else, handle file uploads (append)
        try:
            images = request.FILES.getlist('images')
            added = add_images_to_event(event, images)
            return JsonResponse({'status': 'success', 'added': added, 'event_id': event.id})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)

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
        try:
            video = request.FILES.get('video')
            if not video:
                return JsonResponse({'error': 'No video provided'}, status=400)
            add_or_replace_event_video(event, video)
            return JsonResponse({'status': 'success', 'event_id': event.id})
        except Exception as e:
            # Propagate Cloudinary errors like file too large
            return JsonResponse({'error': str(e)}, status=400)

    elif request.method == 'DELETE':
        success, error = delete_event_video(event, video_id)
        if success:
            return JsonResponse({'status': 'success', 'message': 'Video deleted'})
        else:
            return JsonResponse({'error': error}, status=404)

@csrf_exempt
def login_view(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST method required"}, status=400)
    
    try:
        # Never log raw request bodies; parse JSON directly
        data = json.loads(request.body)
        username = data.get("username")
        password = data.get("password")
        
        if not username or not password:
            return JsonResponse({"error": "Username and password are required"}, status=400)
        
        # Safe, minimal logging in DEBUG only
        if settings.DEBUG:
            logger.debug("Attempting to authenticate user: %s", username)
        
        # Authenticate the user
        user = authenticate(request, username=username, password=password)
        
        if user is None:
            if settings.DEBUG:
                logger.debug("Authentication failed for user: %s", username)
            # Check if user exists but password is wrong
            from django.contrib.auth import get_user_model
            User = get_user_model()
            if User.objects.filter(username=username).exists():
                return JsonResponse({"error": "Invalid password"}, status=401)
            else:
                return JsonResponse({"error": "User does not exist"}, status=401)
                
        if not user.is_active:
            if settings.DEBUG:
                logger.debug("User is inactive: %s", username)
            return JsonResponse({"error": "This account is inactive"}, status=401)
            
        if not user.is_staff:
            if settings.DEBUG:
                logger.debug("User is not staff: %s", username)
            return JsonResponse({"error": "Staff status required"}, status=403)
        
        # If we get here, user is valid and staff
        login(request, user)
        if settings.DEBUG:
            logger.debug("User logged in successfully: %s", username)
        
        return JsonResponse({
            "success": True, 
            "message": "Login successful",
            "user": {
                "username": user.username,
                "is_staff": user.is_staff,
            }
        })
        
    except json.JSONDecodeError:
        if settings.DEBUG:
            logger.debug("Invalid JSON in request body")
        return JsonResponse({"error": "Invalid JSON format"}, status=400)
    except Exception as e:
        if settings.DEBUG:
            logger.exception("Unexpected error during login")
        return JsonResponse({"error": "An error occurred during login"}, status=500)

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
        # Check if user is authenticated and is staff
        if request.user.is_authenticated and request.user.is_staff:
            return JsonResponse({
                "authenticated": True,
                "is_staff": request.user.is_staff,
                "is_superuser": request.user.is_superuser,
                "username": request.user.username,
                "email": request.user.email
            })
        
        # For backward compatibility with existing frontend code
        try:
            data = json.loads(request.body)
            user_name = data.get("user_name")
            email = data.get("email")
            
            if not user_name or not email:
                return JsonResponse({"error": "Username and email are required"}, status=400)
            
            # Check if user exists by username or email
            user = User.objects.filter(username=user_name, email=email).first()
            
            if user and user.is_staff:
                return JsonResponse({
                    "exists": True,
                    "authenticated": request.user.is_authenticated,
                    "is_staff": user.is_staff,
                    "user": {
                        "username": user.username,
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


# ---- Storage analytics (Cloudinary) ----
@csrf_exempt
@require_http_methods(["GET"])
def storage_analytics(request):
    """
    Returns Cloudinary usage totals and per-event usage by summing bytes of resources
    stored under prefixes "<event.name>/" for both images and videos.
    Requires staff authentication.
    """
    if not (request.user.is_authenticated and request.user.is_staff):
        return JsonResponse({"error": "Authentication required"}, status=401)

    try:
        import cloudinary
        from cloudinary import api as cld_api
    except Exception:
        return JsonResponse({"error": "Cloudinary client not installed"}, status=500)

    # Optionally ensure configuration via environment is loaded; django-cloudinary-storage
    # reads from settings.CLOUDINARY_STORAGE.

    # Overall usage
    overall = {}
    try:
        usage = cld_api.usage()
        overall = usage or {}
    except Exception as e:
        overall = {"error": str(e)}

    def sum_resources(prefix: str, resource_type: str):
        total_bytes = 0
        count = 0
        next_cursor = None
        while True:
            try:
                resp = cld_api.resources(type='upload', resource_type=resource_type, prefix=prefix, max_results=500, next_cursor=next_cursor)
            except Exception:
                break
            for r in resp.get('resources', []):
                total_bytes += int(r.get('bytes', 0))
                count += 1
            next_cursor = resp.get('next_cursor')
            if not next_cursor:
                break
        return {"bytes": total_bytes, "count": count}

    per_event = []
    grand_total_bytes = 0
    for ev in Event.objects.all():
        # django-cloudinary-storage uses a root folder 'media' by default
        ev_slug = slugify(ev.name)
        prefix = f"media/{ev_slug}/"
        images = sum_resources(prefix, 'image')
        videos = sum_resources(prefix, 'video')
        ev_total = images["bytes"] + videos["bytes"]
        grand_total_bytes += ev_total
        per_event.append({
            "event_id": ev.id,
            "event_name": ev.name,
            "images": images,
            "videos": videos,
            "total_bytes": ev_total,
        })

    # Compute convenience overall metrics if available
    def parse_usage_block(block: dict):
        if not isinstance(block, dict):
            return None, None, None
        usage = block.get('usage', block.get('used'))
        limit = block.get('limit', block.get('quota'))
        available = None
        try:
            if limit and isinstance(limit, (int, float)) and limit > 0 and isinstance(usage, (int, float)):
                available = max(limit - usage, 0)
        except Exception:
            available = None
        return usage, limit, available

    storage_usage, storage_limit, storage_available = parse_usage_block(overall.get('storage') if isinstance(overall, dict) else None)
    bandwidth_usage, bandwidth_limit, bandwidth_available = parse_usage_block(overall.get('bandwidth') if isinstance(overall, dict) else None)
    transformations_usage, transformations_limit, transformations_available = parse_usage_block(overall.get('transformations') if isinstance(overall, dict) else None)

    # Fallback to environment-defined limits when not provided by Cloudinary API
    notes = []
    try:
        if not isinstance(storage_limit, (int, float)) or storage_limit <= 0:
            lim_gb = os.environ.get('CLOUDINARY_STORAGE_LIMIT_GB')
            if lim_gb:
                storage_limit = float(lim_gb) * 1024 * 1024 * 1024
                if isinstance(storage_usage, (int, float)):
                    storage_available = max(storage_limit - storage_usage, 0)
                notes.append('storage_limit_from_env')
    except Exception:
        pass
    try:
        if not isinstance(bandwidth_limit, (int, float)) or bandwidth_limit <= 0:
            lim_gb = os.environ.get('CLOUDINARY_BANDWIDTH_LIMIT_GB')
            if lim_gb:
                bandwidth_limit = float(lim_gb) * 1024 * 1024 * 1024
                if isinstance(bandwidth_usage, (int, float)):
                    bandwidth_available = max(bandwidth_limit - bandwidth_usage, 0)
                notes.append('bandwidth_limit_from_env')
    except Exception:
        pass
    try:
        if not isinstance(transformations_limit, (int, float)) or transformations_limit <= 0:
            lim = os.environ.get('CLOUDINARY_TRANSFORMATIONS_LIMIT')
            if lim:
                transformations_limit = float(lim)
                if isinstance(transformations_usage, (int, float)):
                    transformations_available = max(transformations_limit - transformations_usage, 0)
                notes.append('transformations_limit_from_env')
    except Exception:
        pass

    result = {
        "overall": overall,
        "overall_storage": {
            "usage_bytes": storage_usage,
            "limit_bytes": storage_limit,
            "available_bytes": storage_available,
        },
        "overall_bandwidth": {
            "usage_bytes": bandwidth_usage,
            "limit_bytes": bandwidth_limit,
            "available_bytes": bandwidth_available,
        },
        "overall_transformations": {
            "usage": transformations_usage,
            "limit": transformations_limit,
            "available": transformations_available,
        },
        "notes": notes,
        "computed_total_bytes": grand_total_bytes,
        "events": per_event,
    }
    return JsonResponse(result)


# ---- Admin-only signed download URLs ----
@require_http_methods(["GET"])
def download_event_image(request, event_id, image_id):
    if not (request.user.is_authenticated and request.user.is_staff):
        return JsonResponse({"error": "Authentication required"}, status=401)
    if cld_utils is None:
        return JsonResponse({"error": "Cloudinary SDK not available"}, status=500)
    try:
        event = Event.objects.get(id=event_id)
        img = event.images.get(id=image_id)
    except Event.DoesNotExist:
        return JsonResponse({"error": "Event not found"}, status=404)
    except EventImage.DoesNotExist:
        return JsonResponse({"error": "Image not found"}, status=404)

    # Derive public_id from storage name (strip extension)
    name = img.image.name  # e.g., media/event-slug/images/file.jpg
    public_id = os.path.splitext(name)[0]
    # Generate short-lived signed URL for public upload resources
    url, _ = cld_utils.cloudinary_url(
        public_id,
        resource_type='image',
        type='upload',
        sign_url=True,
        secure=True,
        expires_at=int(__import__('time').time()) + 60,
        attachment=True,
    )
    return JsonResponse({"url": url})


@require_http_methods(["GET"])
def download_event_video(request, event_id, video_id):
    if not (request.user.is_authenticated and request.user.is_staff):
        return JsonResponse({"error": "Authentication required"}, status=401)
    if cld_utils is None:
        return JsonResponse({"error": "Cloudinary SDK not available"}, status=500)
    try:
        event = Event.objects.get(id=event_id)
        vid = event.video
        if vid.id != int(video_id):
            return JsonResponse({"error": "Video not found"}, status=404)
    except Event.DoesNotExist:
        return JsonResponse({"error": "Event not found"}, status=404)
    except EventVideo.DoesNotExist:
        return JsonResponse({"error": "Video not found"}, status=404)

    name = vid.video.name  # e.g., media/event-slug/videos/file.mp4
    public_id = os.path.splitext(name)[0]
    url, _ = cld_utils.cloudinary_url(
        public_id,
        resource_type='video',
        type='upload',
        sign_url=True,
        secure=True,
        expires_at=int(__import__('time').time()) + 60,
        attachment=True,
    )
    return JsonResponse({"url": url})
