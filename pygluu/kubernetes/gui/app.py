import argparse
import logging
import os
import re
import multiprocessing

import gunicorn.app.base
from flask import Flask

from .extensions import csrf, socketio
from pygluu.kubernetes.gui.views.main import main_blueprint
from pygluu.kubernetes.gui.views.wizard import wizard_blueprint
from pygluu.kubernetes.helpers import copy_templates


def create_app():
    """
    GUI installer app for gluu cloud native

    - set app config
    - initialize extensions
    - registering blueprints
    - generate urls for static files
    """
    app = Flask(__name__)

    # set app config
    cfg = "pygluu.kubernetes.gui.config.ProductionConfig"
    app.config.from_object(cfg)

    # init csrf
    csrf.init_app(app)
    socketio.init_app(app)

    # register blueprint
    app.register_blueprint(main_blueprint)
    app.register_blueprint(wizard_blueprint)

    @app.context_processor
    def hash_processor():
        def hashed_url(filepath):
            directory, filename = filepath.rsplit('/')
            name, extension = filename.rsplit(".")
            folder = os.path.join(os.path.sep, app.root_path, 'static', directory)
            files = os.listdir(folder)
            for f in files:
                regex = name + "\.[a-z0-9]+\." + extension  # noqa: W605
                if re.match(regex, f):
                    return os.path.join('/static', directory, f)
            return os.path.join('/static', filepath)

        return dict(hashed_url=hashed_url)

    return app


class GluuGunicornApp(gunicorn.app.base.BaseApplication):
    def __init__(self, app, options=None):
        self.options = options or {}
        self.application = app
        super().__init__()

    def load_config(self):
        config = {
            key: value for key, value in self.options.items()
            if key in self.cfg.settings and value is not None
        }
        for key, value in config.items():
            self.cfg.set(key.lower(), value)

    def load(self):
        return self.application


def main():
    """
    App initialization with parser to handle argument from CLI

    Arguments :
        -H --host : define hostname
        -p --port : define port
        -d --debug : override debug value default is False

    Note :
        web logs and socketio is disabled to avoid mixing with system logs
        this make easier to read system logs.
    """
    workers_num = (multiprocessing.cpu_count() * 2) + 1

    parser = argparse.ArgumentParser()
    parser.add_argument("-H", "--host", action="store", default="0.0.0.0")
    parser.add_argument("-p", "--port", action="store", default="5000")
    # parser.add_argument("-d", "--debug", type=bool, action="store",
    #                     default=False,
    #                     help="Enable/Disable debug (default: false)")
    parser.add_argument(
        "-w",
        "--workers",
        default=workers_num,
        help="the number of worker processes for handling requests",
    )

    args = parser.parse_args()
    # host = args.host
    # port = int(args.port)
    # debug = args.debug

    copy_templates()
    app = create_app()

    app.logger.disabled = True
    # log = logging.getLogger('werkzeug')
    logging.getLogger('socketio').setLevel(logging.ERROR)
    logging.getLogger('engineio').setLevel(logging.ERROR)
    # log.disabled = True
    logging.getLogger('werkzeug').disabled = True

    # app.run(host=host, port=port, debug=debug)
    gunicorn_opts = {
        "bind": f"{args.host}:{args.port}",
        "worker_class": "gthread",
        "workers": args.workers,
    }
    GluuGunicornApp(app, gunicorn_opts).run()


if __name__ == "__main__":
    main()