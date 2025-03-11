from django.contrib import admin
from order_app.models import Order,OrderItem,OrderStatusHistory,Payment

# Register your models here.
admin.site.register(Order)
admin.site.register(OrderItem)
admin.site.register(OrderStatusHistory)
admin.site.register(Payment)