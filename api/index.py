import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask

try:
    from server import create_app
    app = create_app()
except Exception as e:
    app = Flask(__name__)
    _err = str(e)
    @app.route('/')
    def error_page():
        return f'<h1>Mr.Creative</h1><p>Init: {_err}</p>', 500
