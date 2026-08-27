import os
from matini.web import create_app
from matini import default_settings

def main():
    app = create_app()
    print(f"Starting Matini Web Frontend on http://{default_settings.WEB_HOST}:{default_settings.WEB_PORT}")
    
    try:
        from livereload import Server
        server = Server(app.wsgi_app)
        server.watch("matini/web/templates/")
        server.watch("matini/web/static/")
        server.serve(
            host=default_settings.WEB_HOST,
            port=default_settings.WEB_PORT,
            debug=default_settings.DEBUG,
            restart_delay=1,
        )
    except Exception as e:
        print(f"Livereload not used ({e}), starting standard Flask runner...")
        app.run(
            host=default_settings.WEB_HOST,
            port=default_settings.WEB_PORT,
            debug=default_settings.DEBUG,
        )

if __name__ == "__main__":
    main()
