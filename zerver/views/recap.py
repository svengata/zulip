from django.http import HttpRequest, HttpResponse
from zerver.lib.response import json_success
from zerver.models import UserProfile
from zerver.lib.recap import get_unread_summary # Import your engine!

def get_recap_backend(request: HttpRequest, user_profile: UserProfile) -> HttpResponse:
    # This function is triggered when a user hits the /json/recap URL
    summary_text = get_unread_summary(user_profile)
    
    # Send the recap back to the browser
    return json_success(request, data={"recap": summary_text})