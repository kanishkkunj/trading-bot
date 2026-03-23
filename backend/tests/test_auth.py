"""Authentication tests."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.auth import UserCreate, UserLogin
from app.services.auth_service import AuthService


@pytest.mark.asyncio
async def test_register_user(db_session: AsyncSession) -> None:
    """Test user registration."""
    auth_service = AuthService(db_session)

    user_data = UserCreate(
        email="test@example.com",
        password="password123",
        full_name="Test User",
    )

    user = await auth_service.register_user(user_data)

    assert user.email == "test@example.com"
    assert user.full_name == "Test User"
    assert user.is_active is True
    assert user.hashed_password != "password123"  # Password should be hashed


@pytest.mark.asyncio
async def test_register_duplicate_email(db_session: AsyncSession) -> None:
    """Test registering with duplicate email fails."""
    auth_service = AuthService(db_session)

    user_data = UserCreate(
        email="duplicate@example.com",
        password="password123",
        full_name="Test User",
    )

    # First registration should succeed
    await auth_service.register_user(user_data)

    # Second registration should fail
    with pytest.raises(ValueError, match="already exists"):
        await auth_service.register_user(user_data)


@pytest.mark.asyncio
async def test_authenticate_user(db_session: AsyncSession) -> None:
    """Test user authentication."""
    auth_service = AuthService(db_session)

    # Create user
    user_data = UserCreate(
        email="auth@example.com",
        password="password123",
        full_name="Auth User",
    )
    await auth_service.register_user(user_data)

    # Authenticate with correct credentials
    login_data = UserLogin(email="auth@example.com", password="password123")
    user = await auth_service.authenticate_user(login_data)

    assert user is not None
    assert user.email == "auth@example.com"

    # Authenticate with wrong password
    login_data = UserLogin(email="auth@example.com", password="wrongpassword")
    user = await auth_service.authenticate_user(login_data)

    assert user is None


@pytest.mark.asyncio
async def test_create_access_token(db_session: AsyncSession) -> None:
    """Test JWT token creation."""
    auth_service = AuthService(db_session)

    token = auth_service.create_access_token("test-user-id")

    assert token is not None
    assert isinstance(token, str)

    # Verify token
    user = await auth_service.get_user_from_token(token)
    # Should return None since user doesn't exist, but token is valid
    assert user is None  # User doesn't exist in DB


@pytest.mark.asyncio
async def test_password_hashing(db_session: AsyncSession) -> None:
    """Test password hashing."""
    auth_service = AuthService(db_session)

    password = "mysecretpassword"
    hashed = auth_service.get_password_hash(password)

    assert hashed != password
    assert auth_service.verify_password(password, hashed) is True
    assert auth_service.verify_password("wrongpassword", hashed) is False
