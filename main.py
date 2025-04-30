from fastapi import FastAPI
from pydantic import BaseModel
from langgraph_agent import invoke_agent
import os
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, Security
from fastapi.security import APIKeyHeader

load_dotenv()

app = FastAPI()
api_key_header = APIKeyHeader(name="X-API-KEY")
async def get_api_key(api_key: str = Security(api_key_header)):
    if api_key != os.environ["SECURITY_API_KEY"]:
        raise HTTPException(
            status_code=403,
            detail="Invalid API Key"
        )
    return api_key
class QueryInput(BaseModel):
    user_query: str

@app.get("/")
async def hello():
    print("received: get")
    return {"message": "help: use post for slash query and user_query and api_key"}

@app.post("/query")
async def query(body: QueryInput, api_key: str = Depends(get_api_key)):
    query = body.user_query
    answer = await invoke_agent(query)
    print("Anser received: ", answer)
    return {"message": answer}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app)