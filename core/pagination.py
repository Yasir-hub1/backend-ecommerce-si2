"""
Custom pagination classes for FashionStore API.
"""
from rest_framework.pagination import PageNumberPagination, CursorPagination


class StandardPagination(PageNumberPagination):
    """
    Standard page number pagination.
    Default page size: 20
    Max page size: 100
    """
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class CatalogPagination(CursorPagination):
    """
    Cursor pagination for catalog listings.
    More efficient for large datasets.
    """
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100
    ordering = '-created_at'
