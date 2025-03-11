from rest_framework.exceptions import APIException

class OrderNotFoundException(APIException):
    status_code = 404
    default_detail = "Order not found."
    default_code = "order_not_found"

class PaymentNotFoundException(APIException):
    status_code = 404
    default_detail = "Payment not found for this order."
    default_code = "payment_not_found"

class InvalidOrderStatusException(APIException):
    status_code = 400
    default_detail = "Invalid status."
    default_code = "invalid_order_status"

class OrderAlreadyCancelledException(APIException):
    status_code = 400
    default_detail = "Order is already cancelled."
    default_code = "order_already_cancelled"

class OrderItemNotFoundException(APIException):
    status_code = 404
    default_detail = "Order item not found."
    default_code = "order_item_not_found"
