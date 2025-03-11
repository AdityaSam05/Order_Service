from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAdminUser, AllowAny
from rest_framework.throttling import UserRateThrottle
from .models import Order, OrderItem, Payment, OrderStatusHistory
from .serializers import OrderSerializer, OrderItemSerializer, PaymentSerializer, OrderStatusHistorySerializer
from django.db import transaction
from .exceptions import (
    OrderNotFoundException,
    PaymentNotFoundException,
    InvalidOrderStatusException,
    OrderAlreadyCancelledException,
    OrderItemNotFoundException,
)

class CustomThrottle(UserRateThrottle):
    rate = "10000/min"  # Allow 10000 requests per minute per user
class OrderViewSet(viewsets.ModelViewSet):
    """Handles Orders CRUD"""
    queryset = Order.objects.all().prefetch_related("order_items", "payment", "status_history")
    serializer_class = OrderSerializer
    lookup_field = "order_id"  # Use order_id for lookups
    throttle_classes = [CustomThrottle]
    
    def get_permissions(self):
        """Allow GET requests for all users, but restrict other methods to admin users."""
        if self.request.method == "GET":
            return [AllowAny()]
        return [IsAdminUser()]
    
    def get_object(self):
        try:
            return super().get_object()
        except:
            raise OrderNotFoundException
    
    def create(self, request, *args, **kwargs):
        """Handles creation of Order along with OrderItems and Payment."""
        with transaction.atomic():  # Ensures atomicity in case of failures
            order_serializer = self.get_serializer(data=request.data)
            order_serializer.is_valid(raise_exception=True)
            order = order_serializer.save()

            # Process Order Items if included in request
            order_items_data = request.data.get("order_items", [])  # Fetch order_items from request
            order_items = []
            for item_data in order_items_data:
                item_serializer = OrderItemSerializer(data=item_data)
                item_serializer.is_valid(raise_exception=True)
                order_items.append(item_serializer.save(order=order))

            return Response(
                {
                    "order": order_serializer.data,
                    "order_items": OrderItemSerializer(order_items, many=True).data,
                },
                status=status.HTTP_201_CREATED,
            )

    def create(self, request, *args, **kwargs):
        """Handles creation of Order along with OrderItems and Payment."""
        with transaction.atomic():
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            order = serializer.save()

            # Log status history
            OrderStatusHistory.objects.create(order=order, status=order.status)

            return Response(serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        """Allows updating order details along with order items & payment."""
        partial = kwargs.pop("partial", False)
        order = self.get_object()
        serializer = self.get_serializer(order, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        """Deletes an order and its associated order items and payment."""
        order = self.get_object()
        order.delete()
        return Response({"message": "Order deleted successfully"}, status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["patch"], url_path="update-status")
    def update_status(self, request, order_id=None):
        """Updates the status of an Order and logs it in OrderStatusHistory."""
        order = self.get_object()
        new_status = request.data.get("status")

        if new_status not in dict(Order.STATUS_CHOICES):
            raise InvalidOrderStatusException

        if new_status == "delivered" and order.payment.payment_status != "success":
            return Response(
                {"error": "Order cannot be marked as delivered without successful payment"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        order.status = new_status
        order.save()

        OrderStatusHistory.objects.create(order=order, status=new_status)

        return Response({"message": f"Order {order.order_id} updated to {new_status}"}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"], url_path="status-history")
    def status_history(self, request, order_id=None):
        """Retrieves the status change history for an order."""
        order = self.get_object()
        self.throttle_classes = [CustomThrottle]
        history = order.status_history.all()
        serializer = OrderStatusHistorySerializer(history, many=True)
        return Response(serializer.data)


class OrderItemViewSet(viewsets.ModelViewSet):
    """Handles Order Items CRUD"""
    serializer_class = OrderItemSerializer
    throttle_classes = [CustomThrottle]

    def get_permissions(self):
        """Allow GET requests for all users, but restrict other methods to admin users."""
        if self.request.method == "GET":
            return [AllowAny()]
        return [IsAdminUser()]

    def get_queryset(self):
        """Retrieve order items for a specific order if order_id is provided."""
        self.throttle_classes = [CustomThrottle]
        order_id = self.kwargs.get("order_id")
        if order_id:
            return OrderItem.objects.filter(order__order_id=order_id)
        return OrderItem.objects.all()
    
    def get_object(self):
        try:
            return super().get_object()
        except:
            raise OrderItemNotFoundException

    def create(self, request, *args, **kwargs):
        """Create one or multiple order items for a given order."""
        order_id = self.kwargs.get("order_id")
        order = get_object_or_404(Order, order_id=order_id)  # Ensure order exists

        # Handle single or multiple items
        order_items_data = request.data if isinstance(request.data, list) else [request.data]

        with transaction.atomic():
            created_items = []
            for item_data in order_items_data:
                serializer = self.get_serializer(data=item_data)
                serializer.is_valid(raise_exception=True)
                created_items.append(serializer.save(order=order))

            return Response(OrderItemSerializer(created_items, many=True).data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        """Deletes an OrderItem and updates the total order amount."""
        order_item = self.get_object()
        order = order_item.order

        with transaction.atomic():
            order_item.delete()
            order.update_total_amount()

        return Response({"message": "Order item deleted"}, status=status.HTTP_204_NO_CONTENT)


class PaymentViewSet(viewsets.ModelViewSet):
    """Handles Payment CRUD"""
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer
    lookup_field = "order_id"
    throttle_classes = [CustomThrottle]

    def get_permissions(self):
        """Allow GET requests for all users, but restrict other methods to admin users."""
        if self.request.method == "GET":
            return [AllowAny()]
        return [IsAdminUser()]

    def create(self, request, *args, **kwargs):
        """Create a Payment only if the order exists and payment doesn't already exist."""
        order_id = request.data.get("order")
        order = get_object_or_404(Order, order_id=order_id)

        # Check if a payment already exists for the order
        if Payment.objects.filter(order=order).exists():
            return Response({"error": "Payment for this order already exists"}, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(order=order)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    def get_object(self):
        try:
            return super().get_object()
        except:
            raise PaymentNotFoundException

    def update(self, request, *args, **kwargs):
        """Update a payment while ensuring valid field updates."""
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="confirm")
    def confirm_payment(self, request, order_id=None):
        """Custom action to confirm payment and mark it as successful."""
        payment = get_object_or_404(Payment, order__order_id=order_id)
        if payment.payment_status == "success":
            return Response({"message": "Payment already marked as successful"}, status=status.HTTP_400_BAD_REQUEST)

        payment.payment_status = "success"
        payment.save()

        # Update order status to shipped
        order = payment.order
        order.status = "shipped"
        order.save()
        OrderStatusHistory.objects.create(order=order, status="shipped")

        return Response({"message": "Payment confirmed successfully"}, status=status.HTTP_200_OK)
