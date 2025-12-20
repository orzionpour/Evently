from contextlib import asynccontextmanager
from fastapi import FastAPI, Response

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    print("Starting up...")
    app.state.started = True
    yield
    # Shutdown actions
    print("Shutting down...")
    app.state.started = False

def create_app() -> FastAPI:
    app = FastAPI(title="Evently Worker Service", version="1.0.0", lifespan=lifespan)

    @app.get("/health")
    async def health(response : Response):
        response.status_code = 200

        if not app.state.started:
            response.status_code = 503

        return {"ok": app.state.started}

    return app   

app = create_app()
