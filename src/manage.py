#!/usr/bin/env python
import importlib

import click
from app import app


@click.group()
@click.version_option()
@click.option(
    '--config',
    default='configs',
    help="""默认使用: configs, 所有的 config 都在 configs 目录下.
         例如:configs.your_config""")
def cli(config):
    """Sanic 项目管理工具
    """
    # 加载配置模块
    click.echo('\nUsing config: %s\n' % config)
    config_object = importlib.import_module(config)
    app.config.from_object(config_object)


@cli.command('runserver')
def runserver():
    """
    运行服务器
    """
    from app.server import run_server

    run_server()


if __name__ == '__main__':
    cli()
