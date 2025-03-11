from rest_framework import permissions

class IsAdminUser(permissions.BasePermission):
    """
    Custom permission to allow only admin users to access certain views.
    """
    def has_permission(self, request, view):
        return request.user and request.user.is_staff  # Only allow admin users

class IsOwnerOrAdmin(permissions.BasePermission):
    """
    Custom permission to allow customers to access their own orders
    while allowing admin users to access all orders.
    """
    def has_object_permission(self, request, view, obj):
        return request.user.is_staff or obj.customer_id == request.user.id  # Admins or owners only
