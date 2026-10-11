from fastapi import APIRouter

from ..responses import HEALTH, reply

router = APIRouter()


@router.get("/health")
async def health():
    return reply(HEALTH)  # no DB access
