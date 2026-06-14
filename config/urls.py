"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
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

from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/core/", include("apps.core.urls")),
    path('api/v1/auth/',        include('apps.users.urls')),
    path('api/v1/inventory/',   include('apps.inventory.urls')),
    path('api/v1/procurement/', include('apps.procurement.urls')),
    path('api/v1/sales/',       include('apps.sales.urls')),
    path('api/v1/logistics/',   include('apps.logistics.urls')),
    path('api/v1/production/',  include('apps.production.urls')),
    path('api/v1/finance/',     include('apps.finance.urls')),
    path('api/v1/hr/',          include('apps.hr.urls')),
    path('api/v1/safety/',      include('apps.safety.urls')),
    path('api/v1/messaging/',   include('apps.messaging.urls')),
    path('api/v1/email/',       include('apps.email_client.urls')),
]
