"""
Serializers for branches app.
"""
from rest_framework import serializers
from branches.models import City, Branch


class CitySerializer(serializers.ModelSerializer):
    """City serializer."""

    class Meta:
        model = City
        fields = [
            'id',
            'name',
            'department',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class BranchSerializer(serializers.ModelSerializer):
    """Branch serializer with city details."""
    city_name = serializers.CharField(source='city.name', read_only=True)
    department = serializers.CharField(source='city.department', read_only=True)

    class Meta:
        model = Branch
        fields = [
            'id',
            'code',
            'name',
            'city',
            'city_name',
            'department',
            'address',
            'latitude',
            'longitude',
            'phone',
            'opens_at',
            'closes_at',
            'fitting_rooms',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class BranchListSerializer(serializers.ModelSerializer):
    """Simplified branch serializer for list views."""
    city_name = serializers.CharField(source='city.name', read_only=True)

    class Meta:
        model = Branch
        fields = [
            'id',
            'code',
            'name',
            'city_name',
            'address',
            'latitude',
            'longitude',
            'opens_at',
            'closes_at',
            'fitting_rooms',
            'is_active',
        ]
