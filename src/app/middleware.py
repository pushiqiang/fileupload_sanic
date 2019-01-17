from libs.exceptions import APIException


async def authenticate(request):
    """
    认证
    """
    # 校验认证信息
    ticket = request.cookies.get('ticket', None)
    # if not ticket:
    #     raise APIException(error_type='unauthorized', error_message='无ticket信息')
