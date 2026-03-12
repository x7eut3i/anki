from pydantic import BaseModel, EmailStr, Field


class UserRegister(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: str = Field(max_length=255)
    password: str = Field(min_length=6, max_length=128)


class UserLogin(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    is_active: bool
    is_admin: bool
    session_card_limit: int
    desired_retention: float
    ai_import_batch_size: int
    timezone: str
    study_question_mode: str
    study_custom_ratio: int

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    email: str | None = None
    session_card_limit: int | None = None
    desired_retention: float | None = None
    ai_import_batch_size: int | None = None
    timezone: str | None = None
    study_question_mode: str | None = None
    study_custom_ratio: int | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=6, max_length=128)
