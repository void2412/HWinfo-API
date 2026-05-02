from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from api.routes import router
from config import settings
from hwinfo.reader import read_sensors

_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

app = FastAPI(title="HWInfo Sensor API", version="1.0.0")
app.include_router(router)


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    sensors = read_sensors()
    grouped: dict[str, list] = {}
    if sensors:
        for s in sensors:
            grouped.setdefault(s.type, []).append(s)
    return templates.TemplateResponse(
        request=request,
        name="status.html",
        context={"online": sensors is not None, "grouped": grouped},
    )


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
    )
