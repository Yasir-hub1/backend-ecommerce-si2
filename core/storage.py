"""Storage helpers that replace existing media instead of inventing suffixes."""

from __future__ import annotations

from django.core.files.storage import FileSystemStorage


class OverwriteStorage(FileSystemStorage):
    """
    Default FileSystemStorage renames on collision (beige_AbC123.png).

    AR assets use a stable path per product/color. Without overwrite, the admin
    uploads a real shirt but the IDE / CDN keep serving the old gray seed file
    that still sits at beige.png while Django stores beige_xyz.png.
    """

    def get_available_name(self, name, max_length=None):
        if self.exists(name):
            self.delete(name)
        return super().get_available_name(name, max_length=max_length)
