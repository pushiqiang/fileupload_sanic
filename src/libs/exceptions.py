class APIException(Exception):
    """api 异常
    """
    error_type = 'api_error'
    error_message = 'A server error occurred.'

    def __init__(self, error_type=None, error_message=None):
        if error_type is not None:
            self.error_type = error_type
        if error_message is not None:
            self.error_message = error_message

    def __repr__(self):
        return '<{} {}: {}>'.format(self.__class__, self.error_type,
                                    self.error_message)


class InvalidJSON(APIException):
    error_type = 'invalid_json'
    error_message = 'Request body is not invalid json data'


class WrongRequestFormat(APIException):
    error_type = 'wrong_request_format'
    error_message = 'Request body format wrong'
