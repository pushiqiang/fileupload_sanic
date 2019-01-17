import os
import uuid
import aiofiles
from sanic.blueprints import Blueprint
from sanic.response import json
from views.utils import FileStream, aiowrap
import configs

api_blueprint = Blueprint('file_batch_upload', version='1')

aios = aiowrap(os)


@api_blueprint.post('/upload', stream=True)
async def upload(request):
    bucket = uuid.uuid4().hex
    bucket_dir = os.path.join(configs.MEDIA_DIR, bucket)
    await aios.makedirs(bucket_dir)
    stream = FileStream(request)
    async for file in stream:
        if file.filename:
            async with aiofiles.open(os.path.join(bucket_dir, file.filename), 'wb') as f:
                async for chuck in file:
                    await f.write(chuck)
        else:
            # 没有filename的是其它类型的form参数
            arg = await file.read()
            print(f"Form参数：{file.name}={arg.decode()}")

    return json({'ok': True, 'bucket': bucket})
