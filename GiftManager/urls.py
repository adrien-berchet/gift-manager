"""URL configuration for GiftManager project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/

Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

# from django.conf import settings
from debug_toolbar.toolbar import debug_toolbar_urls
from django.conf.urls.i18n import i18n_patterns

# from django.conf.urls.static import static
from django.contrib import admin
from django.shortcuts import redirect
from django.urls import include
from django.urls import path

from . import views


def admin_redirect(request):  # noqa: ARG001
    return redirect("/admin/")


urlpatterns = [
    path("admin/", admin.site.urls),
    path("admin_redirect/", admin_redirect, name="admin_redirect"),
    path("i18n/", include("django.conf.urls.i18n")),
    path("accounts/login/", views.CustomLoginView.as_view(), name="account_login"),
    path(
        "accounts/user_deactivate",
        views.UserAccountDeactivateView.as_view(),
        name="deactivate_account",
    ),
    path("accounts/user_delete", views.UserAccountDeleteView.as_view(), name="delete_account"),
    path(
        "accounts/user_reactivate/",
        views.UserAccountReactivateView.as_view(),
        name="reactivate_account",
    ),
    path("accounts/", include("allauth.urls")),
    *debug_toolbar_urls(),
]

urlpatterns += i18n_patterns(
    path("", include("gift_manager.urls", namespace="gift_manager")),
)
