from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from database import get_db
from models import CodingResource

router = APIRouter(prefix="/resources", tags=["resources"])


class ResourceCreate(BaseModel):
    title: str
    description: Optional[str] = None
    url: str
    created_by: str
    sort_order: int = 0


@router.get("")
def list_resources(db: Session = Depends(get_db)):
    rows = db.query(CodingResource).order_by(CodingResource.sort_order, CodingResource.created_at).all()
    return [
        {
            "id": r.id,
            "title": r.title,
            "description": r.description,
            "url": r.url,
            "created_by": r.created_by,
            "sort_order": r.sort_order,
            "created_at": r.created_at,
        }
        for r in rows
    ]


@router.post("")
def create_resource(payload: ResourceCreate, db: Session = Depends(get_db)):
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Resource title is required")
    url = payload.url.strip()
    url_lower = url.lower()
    if not (url_lower.startswith("http://") or url_lower.startswith("https://")):
        raise HTTPException(status_code=400, detail="Resource URL must start with http:// or https://")
    r = CodingResource(
        title=title,
        description=payload.description.strip() if payload.description else None,
        url=url,
        created_by=payload.created_by.strip(),
        sort_order=payload.sort_order,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return {"id": r.id, "message": "Resource added"}


@router.delete("/{resource_id}")
def delete_resource(resource_id: int, db: Session = Depends(get_db)):
    r = db.query(CodingResource).filter(CodingResource.id == resource_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Resource not found")
    db.delete(r)
    db.commit()
    return {"message": "Resource deleted"}


@router.patch("/{resource_id}/reorder")
def reorder_resource(resource_id: int, sort_order: int = Query(...), db: Session = Depends(get_db)):
    r = db.query(CodingResource).filter(CodingResource.id == resource_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Resource not found")
    r.sort_order = sort_order
    db.commit()
    return {"message": "Updated"}
