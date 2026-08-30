from django.urls import path

from ai.views import BrowsingEventView, ChatView, RecommendationsView

urlpatterns = [
    path('chat/', ChatView.as_view(), name='ai-chat'),
    path('recommendations/', RecommendationsView.as_view(), name='ai-recommendations'),
    path('events/', BrowsingEventView.as_view(), name='ai-events'),
]
