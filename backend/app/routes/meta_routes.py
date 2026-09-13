from fastapi import APIRouter, Depends

from app.state import AppState, get_state, require_auth
from app.version import VERSION

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/meta", dependencies=[Depends(require_auth)])
async def meta(state: AppState = Depends(get_state)):
    """版本/点数余量/最后采样时间（unix 秒）。"""
    return {
        "mock": state.mock,
        "last_sample_at": state.last_sample_at,
        "rate_limit": state.rate_limit_cache,
        "version": VERSION,
    }
