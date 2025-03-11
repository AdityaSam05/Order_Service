import uuid
import random
from django.db import models, connection
from django.utils.timezone import now
from pytz import timezone

IST = timezone("Asia/Kolkata")

def generate_order_id():
    """Generate a unique 7-digit order ID."""
    while True:
        order_id = str(random.randint(1000000, 9999999))
        if not Order.objects.filter(order_id=order_id).exists():
            return order_id

def get_current_ist_time():
    return now().astimezone(IST).time()

class Order(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("shipped", "Shipped"),
        ("delivered", "Delivered"),
    ]

    order_id = models.CharField(
        max_length=20, unique=True, primary_key=True, default=generate_order_id, db_column="ORDER_ID"
    )
    customer_id = models.CharField(max_length=50, db_column="CUSTOMER_ID")
    address_id = models.IntegerField(db_column="ADDRESS_ID")
    order_date = models.DateField(auto_now_add=True, db_column="ORDER_DATE")
    order_time = models.TimeField(default=get_current_ist_time, db_column="ORDER_TIME")
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, db_column="TOTAL_AMOUNT")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending", db_column="STATUS")
    created_at = models.DateTimeField(auto_now_add=True, db_column="CREATED_AT")
    updated_at = models.DateTimeField(auto_now=True, db_column="UPDATED_AT")

    class Meta:
        db_table = "ORDER_APP_ORDER"

    def update_total_amount(self):
        from django.db.models import Sum
        self.total_amount = self.order_items.aggregate(total=Sum("total_price"))["total"] or 0.00
        self.save()

    def save(self, *args, **kwargs):
        # Validate Customer ID
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT COUNT(*) FROM "KUBORDER_SCHEMA"."CUSTOMERS_CUSTOMER" WHERE "CUSTOMER_ID" = %s',
                [self.customer_id]
            )
            result = cursor.fetchone()
        if result[0] == 0:
            raise ValueError("Invalid customer ID")

        super().save(*args, **kwargs)

    def __str__(self):
        return f"Order {self.order_id} - {self.status}"

class OrderStatusHistory(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="status_history", db_column="ORDER_ID")
    status = models.CharField(max_length=20, db_column="STATUS")
    changed_at = models.DateTimeField(auto_now_add=True, db_column="CHANGED_AT")

    class Meta:
        db_table = "ORDER_APP_ORDER_STATUS_HISTORY"

    def __str__(self):
        return f"Order {self.order.order_id} - {self.status} at {self.changed_at}"

class OrderItem(models.Model):
    order_item_id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False, db_column="ORDER_ITEM_ID"
    )
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="order_items", db_column="ORDER_ID")
    product_id = models.CharField(max_length=50, db_column="PRODUCT_ID")
    quantity = models.PositiveIntegerField(db_column="QUANTITY")
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, db_column="UNIT_PRICE")
    total_price = models.DecimalField(max_digits=10, decimal_places=2, editable=False, db_column="TOTAL_PRICE")
    created_at = models.DateTimeField(auto_now_add=True, db_column="CREATED_AT")
    updated_at = models.DateTimeField(auto_now=True, db_column="UPDATED_AT")

    class Meta:
        db_table = "ORDER_APP_ORDER_ITEM"

    def save(self, *args, **kwargs):
        # Check Product Stock
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT STOCK FROM "KUBORDER_SCHEMA"."PRODUCT_APP_PRODUCT" WHERE "PRODUCT_ID" = %s',
                [self.product_id]
            )
            result = cursor.fetchone()
        if result is None:
            raise ValueError("Invalid product ID")
        available_stock = result[0]
        if available_stock < self.quantity:
            raise ValueError("Insufficient stock for product")
        
        # Calculate total price
        self.total_price = self.unit_price * self.quantity
        super().save(*args, **kwargs)
        self.order.update_total_amount()
        
        # Update product stock after saving the order item
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE KUBORDER_SCHEMA.PRODUCT_APP_PRODUCT SET STOCK = STOCK - %s WHERE PRODUCT_ID = %s",
                [self.quantity, self.product_id]
            )

    def __str__(self):
        return f"Order {self.order.order_id} - Product {self.product_id}"

class Payment(models.Model):
    PAYMENT_METHODS = [
        ("upi", "UPI"),
        ("card", "Card"),
        ("net_banking", "Net Banking"),
        ("cash_on_delivery", "Cash on Delivery"),
    ]

    PAYMENT_STATUS = [
        ("success", "Success"),
        ("pending", "Pending"),
        ("failed", "Failed"),
    ]

    payment_id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False, db_column="PAYMENT_ID"
    )
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="payment", db_column="ORDER_ID", unique=True)
    payment_date = models.DateTimeField(null=True, blank=True, db_column="PAYMENT_DATE")
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, db_column="PAYMENT_METHOD")
    transaction_id = models.CharField(max_length=12, unique=True, null=True, blank=True, db_column="TRANSACTION_ID")
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, db_column="AMOUNT_PAID")
    payment_status = models.CharField(max_length=10, choices=PAYMENT_STATUS, db_column="PAYMENT_STATUS")

    class Meta:
        db_table = "ORDER_APP_PAYMENT"

    def generate_transaction_id(self):
        """Generate a unique 12-digit transaction ID."""
        while True:
            transaction_id = str(uuid.uuid4().int)[:12]
            if not Payment.objects.filter(transaction_id=transaction_id).exists():
                return transaction_id

    def save(self, *args, **kwargs):
        """Assigns transaction ID on successful payment."""
        if self.payment_status == "success":
            if not self.transaction_id:
                self.transaction_id = self.generate_transaction_id()
            self.payment_date = now().astimezone(IST)
            self.amount_paid = self.order.total_amount
        else:
            self.transaction_id = None
            self.payment_date = None
            self.amount_paid = None
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Payment {self.payment_id} - {self.payment_status}"
