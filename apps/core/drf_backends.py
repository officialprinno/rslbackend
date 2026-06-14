"""
DRF filter backends compatible with Daphne/ASGI.

Under ASGI, filter backends may receive a raw ``ASGIRequest`` instead of DRF's
``Request`` wrapper. These backends fall back to ``request.GET`` when needed.
"""

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.fields import CharField
from rest_framework.filters import OrderingFilter, SearchFilter, search_smart_split


def get_query_params(request):
    """Return query params from a DRF or Django/ASGI request."""
    return getattr(request, "query_params", request.GET)


class FMSDjangoFilterBackend(DjangoFilterBackend):
    def get_filterset_kwargs(self, request, queryset, view):
        return {
            "data": get_query_params(request),
            "queryset": queryset,
            "request": request,
        }


class FMSSearchFilter(SearchFilter):
    def get_search_terms(self, request):
        value = get_query_params(request).get(self.search_param, "")
        field = CharField(trim_whitespace=False, allow_blank=True)
        cleaned_value = field.run_validation(value)
        return search_smart_split(cleaned_value)


class FMSOrderingFilter(OrderingFilter):
    def get_ordering(self, request, queryset, view):
        params = get_query_params(request).get(self.ordering_param)
        if params:
            fields = [param.strip() for param in params.split(",")]
            ordering = self.remove_invalid_fields(queryset, fields, view, request)
            if ordering:
                return ordering
        return self.get_default_ordering(view)
