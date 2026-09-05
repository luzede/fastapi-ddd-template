"""Dependency injection wiring for the auth module.

Produces repositories, services and settings. Route guards and cookie management live in
`guards.py` and `cookies.py` respectively, re-exported here for convenience.
"""

from typing import Annotated

from fastapi import Depends

from app.core.config import AuthSettings, Settings, get_settings
from app.modules.auth.access_control import AccessControl
from app.modules.auth.mailer import Mailer
from app.modules.auth.repository import (
    AccountRepository,
    ApiKeyRepository,
    JwksRepository,
    SessionRepository,
    UserRepository,
    VerificationRepository,
)
from app.modules.auth.services.account import AccountService
from app.modules.auth.services.admin import AdminService
from app.modules.auth.services.api_key import ApiKeyService
from app.modules.auth.services.credential import CredentialService
from app.modules.auth.services.email_address import EmailAddressService
from app.modules.auth.services.jwt import JwtService
from app.modules.auth.services.session import SessionService
from app.modules.auth.services.verification import VerificationService
from app.shared.db.session import SessionDep
from app.shared.state import AppStateDep

# --- settings ----------------------------------------------------------------------------


def get_auth_settings(
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthSettings:
    return settings.auth


AuthSettingsDep = Annotated[AuthSettings, Depends(get_auth_settings)]


def get_mailer(state: AppStateDep) -> Mailer:
    return state.mailer


def get_access_control(settings: AuthSettingsDep) -> AccessControl:
    return AccessControl(settings.admin)


AccessControlDep = Annotated[AccessControl, Depends(get_access_control)]

# --- repositories ------------------------------------------------------------------------


def get_user_repository(db: SessionDep) -> UserRepository:
    return UserRepository(db)


def get_session_repository(db: SessionDep) -> SessionRepository:
    return SessionRepository(db)


def get_account_repository(db: SessionDep) -> AccountRepository:
    return AccountRepository(db)


def get_verification_repository(db: SessionDep) -> VerificationRepository:
    return VerificationRepository(db)


def get_jwks_repository(db: SessionDep) -> JwksRepository:
    return JwksRepository(db)


def get_api_key_repository(db: SessionDep) -> ApiKeyRepository:
    return ApiKeyRepository(db)


# --- services ----------------------------------------------------------------------------


def get_session_service(
    repo: Annotated[SessionRepository, Depends(get_session_repository)],
    settings: AuthSettingsDep,
) -> SessionService:
    return SessionService(repo, settings.session)


def get_verification_service(
    repo: Annotated[VerificationRepository, Depends(get_verification_repository)],
    settings: AuthSettingsDep,
) -> VerificationService:
    return VerificationService(repo, settings.secret.get_secret_value())


def get_email_address_service(
    settings: AuthSettingsDep,
    users: Annotated[UserRepository, Depends(get_user_repository)],
    verifications: Annotated[VerificationService, Depends(get_verification_service)],
    mailer: Annotated[Mailer, Depends(get_mailer)],
) -> EmailAddressService:
    return EmailAddressService(
        settings=settings,
        users=users,
        verifications=verifications,
        mailer=mailer,
    )


def get_credential_service(
    settings: AuthSettingsDep,
    users: Annotated[UserRepository, Depends(get_user_repository)],
    accounts: Annotated[AccountRepository, Depends(get_account_repository)],
    sessions: Annotated[SessionService, Depends(get_session_service)],
    verifications: Annotated[VerificationService, Depends(get_verification_service)],
    email_address: Annotated[EmailAddressService, Depends(get_email_address_service)],
    mailer: Annotated[Mailer, Depends(get_mailer)],
) -> CredentialService:
    return CredentialService(
        settings=settings,
        users=users,
        accounts=accounts,
        sessions=sessions,
        verifications=verifications,
        email_address=email_address,
        mailer=mailer,
    )


def get_account_service(
    users: Annotated[UserRepository, Depends(get_user_repository)],
    accounts: Annotated[AccountRepository, Depends(get_account_repository)],
    sessions: Annotated[SessionService, Depends(get_session_service)],
    credentials: Annotated[CredentialService, Depends(get_credential_service)],
) -> AccountService:
    return AccountService(
        users=users,
        accounts=accounts,
        sessions=sessions,
        credentials=credentials,
    )


def get_jwt_service(
    repo: Annotated[JwksRepository, Depends(get_jwks_repository)],
    settings: AuthSettingsDep,
) -> JwtService:
    return JwtService(repo, settings)


def get_api_key_service(
    repo: Annotated[ApiKeyRepository, Depends(get_api_key_repository)],
    settings: AuthSettingsDep,
) -> ApiKeyService:
    return ApiKeyService(repo, settings.api_key)


def get_admin_service(
    settings: AuthSettingsDep,
    access_control: Annotated[AccessControl, Depends(get_access_control)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
    accounts: Annotated[AccountRepository, Depends(get_account_repository)],
    sessions: Annotated[SessionService, Depends(get_session_service)],
) -> AdminService:
    return AdminService(
        settings=settings,
        access_control=access_control,
        users=users,
        accounts=accounts,
        sessions=sessions,
    )


SessionServiceDep = Annotated[SessionService, Depends(get_session_service)]
VerificationServiceDep = Annotated[
    VerificationService, Depends(get_verification_service)
]
EmailAddressServiceDep = Annotated[
    EmailAddressService, Depends(get_email_address_service)
]
CredentialServiceDep = Annotated[CredentialService, Depends(get_credential_service)]
AccountServiceDep = Annotated[AccountService, Depends(get_account_service)]
JwtServiceDep = Annotated[JwtService, Depends(get_jwt_service)]
ApiKeyServiceDep = Annotated[ApiKeyService, Depends(get_api_key_service)]
AdminServiceDep = Annotated[AdminService, Depends(get_admin_service)]

__all__ = [
    "AccessControlDep",
    "AccountServiceDep",
    "AdminServiceDep",
    "ApiKeyServiceDep",
    "AuthSettingsDep",
    "CredentialServiceDep",
    "EmailAddressServiceDep",
    "JwtServiceDep",
    "SessionServiceDep",
    "VerificationServiceDep",
    "get_access_control",
    "get_account_repository",
    "get_account_service",
    "get_admin_service",
    "get_api_key_repository",
    "get_api_key_service",
    "get_auth_settings",
    "get_credential_service",
    "get_email_address_service",
    "get_jwks_repository",
    "get_jwt_service",
    "get_mailer",
    "get_session_repository",
    "get_session_service",
    "get_user_repository",
    "get_verification_repository",
    "get_verification_service",
]
