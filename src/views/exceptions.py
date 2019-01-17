from libs.exceptions import APIException


class ExampleException(APIException):
    error_type = 'example_exception'
    error_message = 'Example exception'
