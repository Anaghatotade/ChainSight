from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import hash_password, verify_password, create_access_token
from app.models import models as m
from app.schemas import schemas as sch
from app.api.deps import get_current_user

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", response_model=sch.Token, status_code=status.HTTP_201_CREATED)
def register(payload: sch.UserCreate, db: Session = Depends(get_db)):
    existing = db.query(m.User).filter(m.User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = m.User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role if payload.role in ("admin", "analyst", "viewer") else "analyst",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(subject=user.email, extra_claims={"role": user.role})
    return sch.Token(access_token=token, user=sch.UserOut.model_validate(user))


@router.post("/login", response_model=sch.Token)
def login(payload: sch.UserLogin, db: Session = Depends(get_db)):
    user = db.query(m.User).filter(m.User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")
    token = create_access_token(subject=user.email, extra_claims={"role": user.role})
    return sch.Token(access_token=token, user=sch.UserOut.model_validate(user))


@router.get("/me", response_model=sch.UserOut)
def me(current_user: m.User = Depends(get_current_user)):
    return current_user
