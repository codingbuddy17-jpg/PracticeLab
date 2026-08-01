"""Shared constants and helpers used across practicelab sub-routers."""
from models import Specialty
from config import settings

IP_SPECIALTIES = {Specialty.IP_DRG}

# NOTE: "ED" here means Edits & Denials (rubric-graded), NOT Emergency Department.
# Emergency Dept specialties are ED_FACILITY / ED_PROFEE / ED_SINGLE_PATH below.
ED_SPECIALTIES = {Specialty.EDITS, Specialty.DENIALS}

# Professional-claim specialties (CMS-1500 / 837P). Every professional claim
# carries diagnosis pointers linking each CPT line to the diagnoses justifying
# it; facility claims (UB-04 / 837I) have none.
POINTER_SPECIALTIES = {
    Specialty.SURGERY,
    Specialty.ED_PROFEE,
    Specialty.EM,
}

# Diagnosis-only work — CPTs are auto-coded upstream in most orgs, so the coder
# enters no procedures. These need their own weights; borrowing the OP config
# would hand out the full CPT weight for free.
DX_ONLY_SPECIALTIES = {Specialty.ANCILLARY}

SINGLE_PATH_SPECIALTIES = {Specialty.ED_SINGLE_PATH}

DPO_SPECIALTIES = {
    Specialty.IP_DRG,
    Specialty.ED_FACILITY,
    Specialty.SDS,
    Specialty.SURGERY,
    Specialty.ANCILLARY,
    Specialty.ED_SINGLE_PATH,
}

MASTER_PASSPHRASE = settings.MASTER_ADMIN_PASSPHRASE


def _is_ip(specialty: Specialty) -> bool:
    return specialty in IP_SPECIALTIES


def _is_ed(specialty: Specialty) -> bool:
    """Edits/Denials rubric grading — not Emergency Department."""
    return specialty in ED_SPECIALTIES


def _is_surgery(specialty: Specialty) -> bool:
    return specialty == Specialty.SURGERY


def _uses_pointers(specialty: Specialty) -> bool:
    return specialty in POINTER_SPECIALTIES


def _is_dx_only(specialty: Specialty) -> bool:
    return specialty in DX_ONLY_SPECIALTIES


def _is_single_path(specialty: Specialty) -> bool:
    return specialty in SINGLE_PATH_SPECIALTIES


def _uses_dpo(specialty: Specialty) -> bool:
    return specialty in DPO_SPECIALTIES
