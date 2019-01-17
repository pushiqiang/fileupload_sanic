import re
import asyncio
import inspect
from functools import wraps, partial
from cgi import parse_header
from urllib.parse import unquote


class FileStream(object):
    """
    Usages:
        stream = FileStream(request)
        async for file in stream:
            if file.filename:
                with open(file.filename, "wb") as f:
                    async for chuck in file:
                        f.write(chuck)
            else:
                # 没有filename的是其它类型的form参数
                arg = await file.read()
                print(f"Form参数：{file.name}={arg.decode()}")
    """
    def __init__(self, request):
        content_type = request.headers.get(
            "Content-Type", "application/octet-stream"
        )
        content_type, parameters = parse_header(content_type)
        if content_type != "multipart/form-data":
            raise ValueError("Must be multipart/form-data")

        self.receive = request.stream.get
        self.boundary = parameters["boundary"].encode("utf-8")
        self.body = b""
        self.closed = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        return await File.from_boundary(self, self.receive, self.boundary)


class File(object):
    mime_type_regex = re.compile(b"Content-Type: (.*)")
    disposition_regex = re.compile(
        rb"Content-Disposition: form-data;"
        rb"(?: name=\"(?P<name>[^;]*?)\")?"
        rb"(?:; filename\*?=\"?"
        rb"(?:(?P<enc>.+?)'"
        rb"(?P<lang>\w*)')?"
        rb"(?P<filename>[^\"]*)\"?)?")

    def __init__(self, stream, receive, boundary, name, filename, mimetype):
        self.mimetype = mimetype
        self.receive = receive
        self.filename = filename
        self.name = name
        self.stream = stream
        self.tmpboundary = b"\r\n--" + boundary
        self.boundary_len = len(self.tmpboundary)
        self._last = b""
        self._size = 0
        self.body_iter = self._iter_content()

    def __aiter__(self):
        return self.body_iter

    def __str__(self):
        return f"<{self.__class__.__name__} " \
               f"name={self.name} " \
               f"filename={self.filename} >"

    def iter_content(self):
        return self.body_iter

    __repr__ = __str__

    async def _iter_content(self):
        stream = self.stream
        while True:
            # 如果存在read过程中剩下的，则直接返回
            if self._last:
                yield self._last
                continue

            index = self.stream.body.find(self.tmpboundary)
            if index != -1:
                # 找到分隔线，返回分隔线前的数据
                # 并将分隔及分隔线后的数据返回给stream
                read, stream.body = stream.body[:index], stream.body[index:]
                self._size += len(read)
                yield read
                if self._last:
                    yield self._last
                break
            else:
                if self.stream.closed:
                    raise RuntimeError("Uncomplete content!")
                # 若没有找到分隔线，为了防止分隔线被读取了一半
                # 选择只返回少于分隔线长度的部分body
                read = stream.body[:-self.boundary_len]
                stream.body = stream.body[-self.boundary_len:]
                self._size += len(read)
                yield read
                await self.get_message(self.receive, stream)

    @staticmethod
    async def get_message(receive, stream):
        message = await receive()
        if not message:
            stream.closed = True
        stream.body += message or b""

    async def read(self, size=10240):
        read = b""
        assert size > 0, (999, "Read size must > 0")
        while len(read) < size:
            try:
                buffer = await self.body_iter.asend(None)
            except StopAsyncIteration:
                return read
            read = read + buffer
            read, self._last = read[:size], read[size:]
        return read

    @classmethod
    async def from_boundary(cls, stream, receive, boundary):
        tmp_boundary = b"--" + boundary
        while not stream.closed:
            await cls.get_message(receive, stream)

            if b"\r\n\r\n" in stream.body and tmp_boundary in stream.body or \
                    stream.closed:
                break

        return cls(stream, receive, boundary, *cls.parse_headers(stream, tmp_boundary))

    @classmethod
    def parse_headers(cls, stream, tmp_boundary):
        end_boundary = tmp_boundary + b"--"
        body = stream.body
        index = body.find(tmp_boundary)
        if index == body.find(end_boundary):
            raise StopAsyncIteration
        body = body[index + len(tmp_boundary):]
        header_str = body[:body.find(b"\r\n\r\n")]
        body = body[body.find(b"\r\n\r\n") + 4:]
        groups = cls.disposition_regex.search(header_str).groupdict()
        filename = groups["filename"] and unquote(groups["filename"].decode())
        if groups["enc"]:
            filename = filename.encode().decode(groups["enc"].decode())
        name = groups["name"].decode()

        mth = cls.mime_type_regex.search(header_str)
        mimetype = mth and mth.group(1).decode()
        stream.body = body
        assert name, "FileStream iterated without File consumed. "
        return name, filename, mimetype


def wrap(func):
    @wraps(func)
    async def run(*args, loop=None, executor=None, **kwargs):
        if loop is None:
            loop = asyncio.get_event_loop()
        pfunc = partial(func, *args, **kwargs)
        return await loop.run_in_executor(executor, pfunc)

    return run


class Wrapper:
    pass


def aiowrap(obj):
    if callable(obj):
        return wrap(obj)
    elif inspect.ismodule(obj) or inspect.isclass(obj):
        wrapped_obj = Wrapper()
        if getattr(obj, '__all__'):
            attrnames = obj.__all__
        else:
            attrnames = dir(obj)
        for attrname in attrnames:
            if attrname.startswith('__'):
                continue
            original_obj = getattr(obj, attrname)
            setattr(wrapped_obj, attrname, aiowrap(original_obj))
        return wrapped_obj
    else:
        return obj
