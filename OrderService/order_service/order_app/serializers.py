from django.utils.timezone import now
from django.db import connection
from rest_framework import serializers
from .models import Order, OrderItem, Payment, OrderStatusHistory

class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = "__all__"
        extra_kwargs = {"order": {"required": False, "allow_null": True}}

class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = "__all__"
        extra_kwargs = {"order": {"required": False}}

class OrderStatusHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderStatusHistory
        fields = "__all__"

class OrderSerializer(serializers.ModelSerializer):
    order_items = OrderItemSerializer(many=True)
    payment = PaymentSerializer(required=False)
    status_history = OrderStatusHistorySerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = "__all__"
        extra_kwargs = {"order_id": {"required": False}}

    def create(self, validated_data):
        order_items_data = validated_data.pop("order_items", [])
        payment_data = validated_data.pop("payment", None)

        order = Order.objects.create(**validated_data)
        for item_data in order_items_data:
            OrderItem.objects.create(order=order, **item_data)

        if payment_data:
            Payment.objects.create(order=order, **payment_data)

        return order
