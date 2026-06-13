"""Shared constants and helpers used across practicelab sub-routers."""
from models import Specialty
from config import settings

IP_SPECIALTIES = {Specialty.IP_DRG}
MASTER_PASSPHRASE = settings.MASTER_ADMIN_PASSPHRASE


def _is_ip(specialty: Specialty) -> bool:
    return specialty in IP_SPECIALTIES
