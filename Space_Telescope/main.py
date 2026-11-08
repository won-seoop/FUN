"""호환용 진입점: `uvicorn main:app` 으로도 실행할 수 있다."""
from app.main import app  # noqa: F401
