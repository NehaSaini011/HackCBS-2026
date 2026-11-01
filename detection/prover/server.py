
import os
import secrets

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from detection.prover.prover import prove_fix


app = FastAPI(
    title="Portfolio Fix Prover",
    description="Verifies proposed database fixes on an isolated database fork.",
    version="1.0.0",
)


class ProveRequest(BaseModel):
    shop: str = Field(default="a")
    customer_id: int = Field(default=62, gt=0)


@app.get("/health")
def health():
    return {"status": "healthy", "service": "prover"}


@app.post("/prove")
def prove(
    request: ProveRequest,
    x_prover_token: str = Header(default="", alias="X-Prover-Token"),
):
    expected_token = os.getenv("PROVER_TOKEN")
    database_url = os.getenv("TIGER_FORK_URI")

    if not expected_token:
        raise HTTPException(
            status_code=503,
            detail="Prover authentication is not configured",
        )

    if not secrets.compare_digest(x_prover_token, expected_token):
        raise HTTPException(
            status_code=401,
            detail="Invalid prover token",
        )

    if not database_url:
        raise HTTPException(
            status_code=503,
            detail="Prover database is not configured",
        )

    if request.shop != "a":
        raise HTTPException(
            status_code=400,
            detail="Currently only Pinecart (shop a) is supported",
        )

    try:
        result = prove_fix(
            database_url=database_url,
            customer_id=request.customer_id,
        )

        return {
            "shop": request.shop,
            **result,
        }

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Prover execution failed. Check server logs.",
        )
