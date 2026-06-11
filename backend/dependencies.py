from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from backend.firebase_setup import verify_token, initialize_firebase

# Ensure firebase is initialized
initialize_firebase()

security = HTTPBearer()


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Verifies the Firebase ID Token and returns the decoded token (user info).
    Same Firebase project as IgniteAI, so IgniteAI sessions work here too.
    """
    token = credentials.credentials
    try:
        return verify_token(token)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication credentials: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
