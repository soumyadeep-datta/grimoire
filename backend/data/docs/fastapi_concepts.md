# FastAPI Core Concepts

## Path Parameters
Path parameters are declared using Python type hints:
```python
@app.get("/items/{item_id}")
async def read_item(item_id: int):
    return {"item_id": item_id}
```
FastAPI automatically validates the type and returns a 422 error if validation fails.

## Query Parameters
Any parameter not in the path is treated as a query parameter:
```python
@app.get("/items/")
async def read_items(skip: int = 0, limit: int = 10):
    return fake_items_db[skip : skip + limit]
```

## Request Body
Use Pydantic models to declare request bodies:
```python
from pydantic import BaseModel

class Item(BaseModel):
    name: str
    price: float
    is_offer: bool = False

@app.post("/items/")
async def create_item(item: Item):
    return item
```

## Dependency Injection
FastAPI has a powerful dependency injection system:
```python
from fastapi import Depends

async def common_parameters(q: str = None, skip: int = 0, limit: int = 100):
    return {"q": q, "skip": skip, "limit": limit}

@app.get("/items/")
async def read_items(commons: dict = Depends(common_parameters)):
    return commons
```

## Background Tasks
Run operations after returning a response:
```python
from fastapi import BackgroundTasks

def write_notification(email: str, message=""):
    with open("log.txt", mode="w") as email_file:
        content = f"notification for {email}: {message}"
        email_file.write(content)

@app.post("/send-notification/{email}")
async def send_notification(email: str, background_tasks: BackgroundTasks):
    background_tasks.add_task(write_notification, email, message="some notification")
    return {"message": "Notification sent in the background"}
```

## Middleware
Add middleware to process every request and response:
```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## Error Handling
Raise HTTPException for HTTP errors:
```python
from fastapi import HTTPException

@app.get("/items/{item_id}")
async def read_item(item_id: int):
    if item_id not in db:
        raise HTTPException(status_code=404, detail="Item not found")
    return db[item_id]
```

## Async Support
FastAPI supports both sync and async endpoints:
```python
# Sync — runs in a thread pool automatically
@app.get("/sync")
def sync_endpoint():
    return {"type": "sync"}

# Async — runs on the event loop
@app.get("/async")
async def async_endpoint():
    return {"type": "async"}
```

## Response Models
Declare response shapes with Pydantic:
```python
class ItemResponse(BaseModel):
    name: str
    price: float

@app.get("/items/{item_id}", response_model=ItemResponse)
async def read_item(item_id: int):
    return get_item(item_id)
```
FastAPI will filter the response to only include fields declared in ItemResponse.

## Testing
FastAPI provides a TestClient for easy testing:
```python
from fastapi.testclient import TestClient

client = TestClient(app)

def test_read_item():
    response = client.get("/items/42")
    assert response.status_code == 200
    assert response.json() == {"item_id": 42}
```