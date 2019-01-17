"""
sanic server
"""
from app import app
from app import middleware

from views.views import api_blueprint
from libs.generics import handle_exception

app.middleware('request')(middleware.authenticate)
app.blueprint(api_blueprint)


@app.exception(Exception)
async def handle_dispatch_exception(request, exception):
    return (await handle_exception(exception))


def run_server():
    """启动服务器
    根据启动参数加载配置, 如果没有相应的配置文件直接抛出错误
    """
    app.run(
        host=app.config.HOST,
        port=app.config.PORT,
        workers=app.config.WORKERS,
        debug=app.config.DEBUG)
