"""FastAPI application entry point for backend.

Registers all routes, middleware, exception handlers, and
lifespan events for the Agent system backend.
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import settings
from core.errors import register_exception_handlers
from core.logging import get_logger, setup_logging
from core.security import get_cors_origins

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Lifespan Events
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler.

    Handles startup and shutdown events.
    """
    # Startup
    logger.info("=" * 60)
    logger.info("Agent Backend v2 Starting Up...")
    logger.info(f"Environment: {settings.log_level}")
    logger.info(f"Database: {settings.async_database_url.split('@')[-1]}")
    logger.info(f"Workspace Root: {settings.workspace_root}")
    logger.info("=" * 60)

    # Initialize database
    try:
        from db.session import init_db

        await init_db()
        logger.info("Database initialized.")
    except Exception as e:
        logger.warning(f"Database initialization skipped: {e}")

    # Register default tools
    try:
        from agent.tool_registry import register_default_tools

        register_default_tools()
        logger.info("Default tools registered.")
    except Exception as e:
        logger.error(f"Tool registration failed: {e}")

    logger.info("Agent Backend v2 is ready!")

    yield

    # Shutdown
    logger.info("Agent Backend v2 Shutting Down...")

    try:
        from db.session import close_db

        await close_db()
        logger.info("Database connection closed.")
    except Exception as e:
        logger.warning(f"Database shutdown error: {e}")

    logger.info("Goodbye!")


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI app instance.
    """
    # Setup logging
    setup_logging(settings.log_level)

    app = FastAPI(
        title="Agent Backend v2",
        description="FastAPI backend for the Agent Workbench System",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register exception handlers
    register_exception_handlers(app)

    # Register routers
    _register_routers(app)

    return app


def _register_routers(app: FastAPI) -> None:
    """Register all API routers."""
    # Import and register all route modules
    from api.chat import router as chat_router
    from api.conversations import router as conversations_router
    from api.workspace import router as workspace_router
    from api.uploads import router as uploads_router
    from api.tools import router as tools_router
    from api.context import router as context_router
    from api.memory import router as memory_router
    from api.models import router as models_router
    from api.api_configs import router as api_configs_router

    app.include_router(chat_router)
    app.include_router(conversations_router)
    app.include_router(workspace_router)
    app.include_router(uploads_router)
    app.include_router(tools_router)
    app.include_router(context_router)
    app.include_router(memory_router)
    app.include_router(models_router)
    app.include_router(api_configs_router)

    logger.info("All API routers registered.")


# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------

app = create_app()


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint.

    Returns:
        Status dictionary.
    """
    return {
        "status": "healthy",
        "version": "1.0.0",
        "service": "agent-backend-v2",
    }


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint.

    Returns:
        Welcome message.
    """
    return {
        "message": "Agent Backend v2",
        "docs": "/docs",
        "health": "/health",
    }


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
        log_level=settings.log_level.lower(),
    )
