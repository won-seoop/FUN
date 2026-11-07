from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def home():
    return {"message": "Space Telescope API Running"}

@app.get("/status")
def status():
    return {"telescope": "not connected"}