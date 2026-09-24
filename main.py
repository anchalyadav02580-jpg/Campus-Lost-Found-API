"""
Lost & Found API
-----------------
FastAPI + SQLModel + SQLite backend for reporting and managing
lost/found items on a college campus.
"""

from enum import Enum
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Depends, status as http_status
from sqlmodel import SQLModel, Field, Session, create_engine, select
from pydantic import field_validator


# ---------------------------------------------------------------------------
# Database setup
# ---------------------------------------------------------------------------
DATABASE_URL = "sqlite:///./lost_and_found.db"

# check_same_thread=False is needed because FastAPI can use the connection
# across different threads within the same request lifecycle.
engine = create_engine(DATABASE_URL, echo=False, connect_args={"check_same_thread": False})


def create_db_and_tables() -> None:
    """Create all tables defined by SQLModel metadata."""
    SQLModel.metadata.create_all(engine)


def get_session():
    """Dependency that yields a database session for a single request."""
    with Session(engine) as session:
        yield session


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class ItemStatus(str, Enum):
    LOST = "Lost"
    FOUND = "Found"
    RETURNED = "Returned"


class ItemCategory(str, Enum):
    ELECTRONICS = "Electronics"
    DOCUMENTS = "Documents"
    ACCESSORIES = "Accessories"
    CLOTHING = "Clothing"
    BOOKS = "Books"
    OTHER = "Other"


# ---------------------------------------------------------------------------
# Database model (this IS the table — SQLModel table=True)
# ---------------------------------------------------------------------------
class Item(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(index=True, min_length=1)
    description: str
    category: ItemCategory
    location: str
    reported_by: str
    status: ItemStatus = Field(default=ItemStatus.LOST)


# ---------------------------------------------------------------------------
# Request/response schemas (kept separate from the table model)
# ---------------------------------------------------------------------------
class ItemCreate(SQLModel):
    title: str
    description: str
    category: ItemCategory
    location: str
    reported_by: str
    status: ItemStatus = ItemStatus.LOST

    @field_validator("title")
    @classmethod
    def title_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("title must not be empty")
        return v.strip()

    @field_validator("description")
    @classmethod
    def description_must_be_meaningful(cls, v: str) -> str:
        if not v or len(v.strip()) < 5:
            raise ValueError("description must contain meaningful text (min 5 characters)")
        return v.strip()

    @field_validator("location")
    @classmethod
    def location_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("location must not be empty")
        return v.strip()

    @field_validator("reported_by")
    @classmethod
    def reported_by_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("reported_by must not be empty")
        return v.strip()


class ItemUpdate(SQLModel):
    """All fields optional — only provided fields get updated (PUT/patch-style)."""
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[ItemCategory] = None
    location: Optional[str] = None
    reported_by: Optional[str] = None
    status: Optional[ItemStatus] = None

    @field_validator("title")
    @classmethod
    def title_not_empty_if_given(cls, v):
        if v is not None and not v.strip():
            raise ValueError("title must not be empty")
        return v.strip() if v else v

    @field_validator("description")
    @classmethod
    def description_meaningful_if_given(cls, v):
        if v is not None and len(v.strip()) < 5:
            raise ValueError("description must contain meaningful text (min 5 characters)")
        return v.strip() if v else v


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Campus Lost & Found API",
    description="Report, track, and resolve lost/found items on campus.",
    version="1.0.0",
)


@app.on_event("startup")
def on_startup():
    create_db_and_tables()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.post("/items", response_model=Item, status_code=http_status.HTTP_201_CREATED, tags=["Items"])
def create_item(item: ItemCreate, session: Session = Depends(get_session)):
    """Create a new lost/found item report."""
    db_item = Item(**item.model_dump())
    session.add(db_item)
    session.commit()
    session.refresh(db_item)
    return db_item


@app.get("/items", response_model=List[Item], tags=["Items"])
def read_items(session: Session = Depends(get_session)):
    """Return all reported items."""
    return session.exec(select(Item)).all()


@app.get("/items/status/{item_status}", response_model=List[Item], tags=["Items"])
def read_items_by_status(item_status: ItemStatus, session: Session = Depends(get_session)):
    """Return all items with the given status (Lost, Found, Returned)."""
    results = session.exec(select(Item).where(Item.status == item_status)).all()
    return results


@app.get("/items/category/{item_category}", response_model=List[Item], tags=["Items"])
def read_items_by_category(item_category: ItemCategory, session: Session = Depends(get_session)):
    """Return all items belonging to a particular category."""
    results = session.exec(select(Item).where(Item.category == item_category)).all()
    return results


@app.get("/items/{item_id}", response_model=Item, tags=["Items"])
def read_item(item_id: int, session: Session = Depends(get_session)):
    """Return a single item by ID, or 404 if it doesn't exist."""
    item = session.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=f"Item with id {item_id} not found")
    return item


@app.put("/items/{item_id}", response_model=Item, tags=["Items"])
def update_item(item_id: int, item_update: ItemUpdate, session: Session = Depends(get_session)):
    """Update an existing item's details/status. Only supplied fields change."""
    db_item = session.get(Item, item_id)
    if not db_item:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=f"Item with id {item_id} not found")

    update_data = item_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_item, key, value)

    session.add(db_item)
    session.commit()
    session.refresh(db_item)
    return db_item


@app.delete("/items/{item_id}", status_code=http_status.HTTP_204_NO_CONTENT, tags=["Items"])
def delete_item(item_id: int, session: Session = Depends(get_session)):
    """Delete an item report by ID."""
    db_item = session.get(Item, item_id)
    if not db_item:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=f"Item with id {item_id} not found")
    session.delete(db_item)
    session.commit()
    return None
