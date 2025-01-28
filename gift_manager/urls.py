from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path
from . import views

app_name = 'gift_manager'

urlpatterns = [
    path('', views.home, name='home'),
    path('admin/', admin.site.urls),
    path('persons/', views.PersonListView.as_view(), name='persons'),
    path('persons/create/', views.PersonCreateView.as_view(), name='person_create'),
    path('gifts/', views.GiftListView.as_view(), name='gifts'),
    path('gifts/create/', views.GiftCreateView.as_view(), name='gift_create'),
    path('events/', views.EventListView.as_view(), name='events'),
    path('events/create/', views.EventCreateView.as_view(), name='event_create'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
