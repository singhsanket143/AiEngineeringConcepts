from datetime import datetime, timezone
import json
from pathlib import Path
import threading
from uuid import uuid4
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import BaseModel
from typing import Annotated, Literal

mcp = FastMCP(
    name="Todo",
    instructions=(
        "A simple todo list. Use create_todo, list_todos, get_todo, "
        "update_todo, and delete_todo to manage your todos."
    )
)

Status = Literal["pending", "completed", "deleted"]

STORE_PATH = Path(__file__).with_name("todos.json") # local file to store todos

_lock = threading.Lock() # lock to synchronize access to the store

class Todo(BaseModel):
    id: str 
    title: str 
    description: str = "" 
    status: Status = "pending"
    created_at: str 
    updated_at: str 


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def _load() -> dict[str, Todo]:
    if not STORE_PATH.exists():
        return {}
    raw = json.loads(STORE_PATH.read_text() or "[]")
    return {item["id"]: Todo.model_validate(item) for item in raw}

def _save(todos: dict[str, Todo]) -> None:
    STORE_PATH.write_text(
        json.dumps([todo.model_dump() for todo in todos.values()], indent=2) + "\n"
    )

def _get_or_raise(todo_id: str) -> tuple[dict[str, Todo], Todo]:
    todos = _load()
    todo = todos.get(todo_id)
    if todo is None:
        raise ValueError(f"Todo with id {todo_id} not found")
    return todos, todo

@mcp.tool
def create_todo(
    title: Annotated[str, "Short title of the todo"],
    description: Annotated[str, "Optional long description"] = "", 
    status: Annotated[Status, "pending, completed, or deleted"] = "pending"
) -> Todo | None:
    """Create a todo and return it."""

    title = title.strip()

    if not title:
        raise ToolError("Title cannot be empty")

    now = _now() 
    todo = Todo(
        id=uuid4().hex[:8],
        title=title,
        description=description.strip(),
        status=status,
        created_at=now,
        updated_at=now,
    )

    with _lock: # we acquire the lock to prevent concurrent access to the store
        todos = _load()
        todos[todo.id] = todo
        _save(todos)
    # we release the lock after we have saved the todo
    return todo

@mcp.tool
def list_todos(
    status: Annotated[Status | None, "pending, completed, deleted or None to list all"] = None
) -> list[Todo]:
    """List todos, newest first. Optionally filter by status."""
    with _lock:
        todos = list(_load().values())
    
    if status is not None:
        todos = [todo for todo in todos if todo.status == status]
    todos.sort(key=lambda todo: todo.created_at, reverse=True)
    return todos

    

@mcp.tool
def get_todo(
    todo_id: Annotated[str, "The ID of the todo to get"]
) -> Todo | None:
    """Get a todo by id"""
    with _lock:
        _, todo = _get_or_raise(todo_id)
    return todo

@mcp.tool
def delete_todo(
    todo_id: Annotated[str, "The ID of the todo to delete"]
) -> str:
    """Delete a todo by id and return the id"""
    with _lock:
        todos, _ = _get_or_raise(todo_id)
        del todos[todo_id] # deleting the todo from the in memory dict
        _save(todos) # saving the todos to the file
    return f"Deleted todo {todo_id}"

@mcp.tool
def update_todo(
    todo_id: Annotated[str, "The ID of the todo to update"],
    title: Annotated[str | None, "New title, or None to leave unchanged"] = None,
    description: Annotated[str | None, "New description, or None to leave unchanged"] = None,
    status: Annotated[Status | None, "pending, completed, deleted or None to leave unchanged"] = None,
) -> Todo:
    """Update a todo's title, description, or status and return it."""
    with _lock:
        todos, todo = _get_or_raise(todo_id)
        if title is not None:
            title = title.strip()
            if not title:
                raise ToolError("Title cannot be empty")
            todo.title = title
        if description is not None:
            todo.description = description.strip()
        if status is not None:
            todo.status = status
        todo.updated_at = _now()
        todos[todo.id] = todo
        _save(todos)
    return todo

@mcp.resource("todo://all")
def todos_resource() -> list[dict]:
    """All todos as a readable resource"""
    with _lock:
        todos = list(_load().values())
    todos.sort(key=lambda todo: todo.created_at, reverse=True)
    return [todo.model_dump() for todo in todos]


if __name__ == "__main__":
    mcp.run(transport="http", host="127.0.0.1", port=8000) 

# Cursor -> mac -> cmd+shft+p windows -> ctrl+shift+p