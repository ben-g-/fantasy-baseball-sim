from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


@app.get('/health')
def health():
    return {'status': 'ok'}


class SimRequest(BaseModel):
    matchup_id: str


@app.post('/sim')
def run_sim(request: SimRequest):
    # TODO Phase 4: implement simulation logic
    raise NotImplementedError('Simulation engine not yet implemented')
