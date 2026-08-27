import uvicorn
from matini.api import create_application
from matini import default_settings

app = create_application()

def main():
    print(f"Starting Matini API Backend on http://{default_settings.API_HOST}:{default_settings.API_PORT}")
    uvicorn.run(
        "matini.cmd.api:app",
        host=default_settings.API_HOST,
        port=default_settings.API_PORT,
        reload=default_settings.DEBUG,
    )

if __name__ == "__main__":
    main()
