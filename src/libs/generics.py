import uuid
import logging
from inspect import isawaitable

from marshmallow.exceptions import ValidationError
from sanic.exceptions import InvalidUsage
from sanic.response import json
from sanic.views import HTTPMethodView

from libs.exceptions import APIException, InvalidJSON, WrongRequestFormat

logger = logging.getLogger(__name__)


def ok_response(body, message="", *args, **kwargs):
    """成功的 response
    """
    new_body = {'ok': True, 'message': message, 'result': body}
    return json(new_body, *args, **kwargs)


def failed_response(error_type, error_message, *args, **kwargs):
    """失败的 response
    """
    body = {'ok': False, 'error_type': error_type, 'message': error_message}
    return json(body, *args, **kwargs)


def validation_error_response(validation_error, *args, **kwargs):
    """字段验证失败的 response
    validation_error: ValidationError
    """
    errors = list()
    for field in validation_error.field_names:
        field_error = {
            'error_type': 'validation_error',
            'field': field,
            'message': validation_error.messages[field][0]
        }
        errors.append(field_error)

    new_body = {'ok': False, 'errors': errors}
    return json(new_body, *args, **kwargs)


async def handle_exception(exception):
    """处理异常
    ValidationError, APIException: 返回适当的错误信息
    else: 重新抛出异常
    """
    if isinstance(exception, ValidationError):
        response = validation_error_response(exception)
    elif isinstance(exception, APIException):
        response = failed_response(
            error_type=exception.error_type,
            error_message=exception.error_message)
    else:
        # 非 debug 模式下, 发送错误消息到 sentry
        # if not app.config.DEBUG:
        #     app.sentry.captureException()
        # raise exception
        response = failed_response(
            error_type='api_error',
            error_message='A server error occurred.')

    logger.error('A server error occurred.', exc_info=exception)
    return response


class APIBaseView(HTTPMethodView):
    """扩展 class based view, 增加异常处理
    """
    args_deserializer_class = None
    path_deserializer_class = None
    deserializer_class = None
    serializer_class = None

    @property
    def kong_user_id(self):
        user_id = self.request.headers.get('x-authenticated-userid', None)
        if user_id:
            return uuid.UUID(user_id)

    def get_context(self):
        return {}

    def parse_json(self, request, many=False):
        """解析 request body 为 json
        如果 many 为 True, 使请求数据为列表
        """
        try:
            parsed_data = request.json
        except InvalidUsage:
            raise InvalidJSON

        if parsed_data is None:
            return {}

        target_type = list if many else dict
        if not isinstance(parsed_data, target_type):
            raise WrongRequestFormat
        return parsed_data

    def parse_request_context(self, request, *args, **kwargs):
        """解析请求上下文
        query_params：parsed query string variables
        path_params：parsed url path string variables
        body_data：parsed body json data
        """
        if self.args_deserializer_class is None:
            self.query_params = request.raw_args
        else:
            # 反序列化验证传入的querystring参数
            self.query_params, _ = self.args_deserializer_class(
                strict=True).load(request.raw_args)

        if self.path_deserializer_class is None:
            self.path_params = kwargs
        else:
            # 反序列化验证传入的path参数
            self.path_params, _ = self.path_deserializer_class(
                strict=True).load(kwargs)

        self.body_data = self.parse_json(request)

    async def dispatch_request(self, request, *args, **kwargs):
        """扩展 http 请求的分发, 添加错误处理
        """
        self.request = request

        try:
            self.parse_request_context(request, *args, **kwargs)
            response = super(APIBaseView, self).dispatch_request(
                request, *args, **kwargs)
            if isawaitable(response):
                response = await response
        except Exception as exception:
            response = await self.handle_exception(exception)

        return response

    async def handle_exception(self, exception):
        """处理异常
        ValidationError, APIException: 返回适当的错误信息
        else: 重新抛出异常
        """
        return await handle_exception(exception)

    def get_deserializer(self):
        assert self.deserializer_class is not None, (
            "'%s' should either include a `serializer_class` attribute, "
            "or override the `get_deserializer_class()` method." %
            self.__class__.__name__)
        return self.deserializer_class(context=self.get_context(), strict=True)

    def get_serializer(self):
        assert self.serializer_class is not None, (
            "'%s' should either include a `serializer_class` attribute, "
            "or override the `get_serializer_class()` method." %
            self.__class__.__name__)
        return self.serializer_class(context=self.get_context(), strict=True)

    async def validate_data(self, body_data):
        """验证请求数据
        若不需要反序列化验证请求数据，可重写改方法
        """
        validated_data, _ = self.get_deserializer().load(body_data)

        return validated_data


class GetView(APIBaseView):
    """GET api view
    1. 获取数据对象
    2. 序列化数据
    """
    args_deserializer_class = None
    serializer_class = None

    async def get_object(self):
        """获取需要序列化的对象
        """
        raise NotImplementedError

    async def get(self, request, *args, **kwargs):
        """处理 GET 请求
        """
        target_object = await self.get_object()
        serialized_data = await self.retrieve_result_serialize(target_object)
        return ok_response(serialized_data)

    async def retrieve_result_serialize(self, target_object):
        """序列化目标对象
        """
        if self.serializer_class is None:
            return {}
        data, _ = self.get_serializer().dump(target_object)
        return data


class PostView(APIBaseView):
    """创建数据的 view
    1. 验证请求数据
    2. 保存数据
    3. 序列化数据
    """
    args_deserializer_class = None
    deserializer_class = None
    serializer_class = None

    async def post(self, request, *args, **kwargs):
        self.validated_data = await self.validate_data(self.body_data)
        # 保存数据
        saved_object = await self.save()
        serialized_data = await self.create_result_serialize(saved_object)
        return ok_response(serialized_data)

    async def save(self):
        """根据 self.validated_data和self.path_params, self.query_params 保存数据到数据库
        """
        raise NotImplementedError

    async def create_result_serialize(self, saved_object):
        """创建结果响应序列化
        """
        if not self.serializer_class:
            return {}

        data, _ = self.get_serializer().dump(saved_object)
        return data


class UpdateMixin:
    async def save(self):
        """根据 self.validated_data 和 self.path_params, self.query_params
        更新instance对象到数据库
        """
        raise NotImplementedError

    async def update_result_serialize(self, saved_object):
        """更新结果响应序列化
        """
        if not self.serializer_class:
            return {}

        data, _ = self.get_serializer().dump(saved_object)
        return data


class PutView(APIBaseView, UpdateMixin):
    """更新已知资源 view
    1. 验证请求数据
    2. 获取对象
    3. 更新对象
    4. 序列化结果
    """
    args_deserializer_class = None
    deserializer_class = None
    serializer_class = None

    async def put(self, request, *args, **kwargs):
        self.validated_data = await self.validate_data(self.body_data)
        # 保存数据
        patched_object = await self.save()
        serialized_data = await self.update_result_serialize(patched_object)
        return ok_response(serialized_data)


class PatchView(APIBaseView, UpdateMixin):
    """局部更新资源 view
    1. 验证请求数据
    2. 获取对象
    3. 更新对象
    4. 序列化结果
    """
    args_deserializer_class = None
    deserializer_class = None
    serializer_class = None

    async def patch(self, request, *args, **kwargs):
        self.validated_data = await self.validate_data(self.body_data)
        # 保存数据
        patched_object = await self.save()
        serialized_data = await self.update_result_serialize(patched_object)
        return ok_response(serialized_data)


class DeleteView(APIBaseView):
    """删除数据的 view
    1. 获取对象
    2. 删除对象
    3. 序列化结果
    """
    args_deserializer_class = None
    serializer_class = None

    async def delete(self, request, *args, **kwargs):
        # 保存数据
        self.instance = self.get_object()
        deleted_object = await self.destroy(self.instance)
        serialized_data = await self.delete_result_serialize(deleted_object)
        return ok_response(serialized_data)

    async def get_object(self):
        """获取需要序列化的对象
        """
        raise NotImplementedError

    async def destroy(self, instance):
        """根据 self.validated_data 和 self.context 保存数据到数据库
        """
        raise NotImplementedError

    async def delete_result_serialize(self, deleted_object):
        """响应序列化结果
        """
        if not self.serializer_class:
            return {}

        data, _ = self.get_serializer().dump(deleted_object)
        return data


class ListView(APIBaseView):
    """List api view
    1. 获取一组数据
    2. 序列化一组数据
    3. 序列化结果
    """
    args_deserializer_class = None
    serializer_class = None
    result_name = 'items'

    async def get(self, request, *args, **kwargs):
        """处理 GET 请求
        """
        target_objects = await self.get_objects()
        serialized_data = await self.list_result_serialize(target_objects)
        return ok_response(serialized_data)

    async def get_objects(self):
        """获取需要序列化的对象
        """
        raise NotImplementedError

    async def list_result_serialize(self, target_objects):
        """响序列化应结果
        默认返回空 json 对象, 需要修改则在子类中覆盖这个方法
        """
        if not self.serializer_class:
            return {}

        data, _ = self.get_serializer().dump(target_objects, many=True)
        if self.result_name is None:
            return data

        return {self.result_name: data}
