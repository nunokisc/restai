import secrets
from typing import Annotated
from fastapi import Depends, HTTPException

from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.orm import Session

from app.database import get_db, dbc, pwd_context
from app.models import User



security = HTTPBasic()


def get_current_username(
    credentials: Annotated[HTTPBasicCredentials, Depends(security)],
    db: Session = Depends(get_db),
):
    user = dbc.get_user_by_username(db, credentials.username)

    is_correct_username = credentials.username == user.username
    is_correct_password = pwd_context.verify(credentials.password, user.hashed_password)
    
    if not (is_correct_username and is_correct_password):
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    
    return user

def get_current_username_admin(
    user: User = Depends(get_current_username)
):    
    if not (user.is_admin == True):
        raise HTTPException(
            status_code=401,
            detail="Insuficient permissions",
            headers={"WWW-Authenticate": "Basic"},
        )
    return user