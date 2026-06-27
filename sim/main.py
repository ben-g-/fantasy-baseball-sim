from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from sim_service import (
    MatchupNotFoundError,
    MatchupNotScheduledError,
    SimExecutionError,
    run_matchup,
)

app = FastAPI()


@app.get('/health')
def health():
    return {'status': 'ok'}


class SimRequest(BaseModel):
    matchup_id: str


@app.post('/sim')
def run_sim(request: SimRequest):
    try:
        return run_matchup(request.matchup_id)
    except MatchupNotFoundError:
        raise HTTPException(status_code=404, detail='Matchup not found')
    except MatchupNotScheduledError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except SimExecutionError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
