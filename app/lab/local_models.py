"""Polecane modele: pojedynczy przebieg 72 zapytań pakietu PROSTATA-RT, 2026-10-12."""
from dataclasses import dataclass
import ctypes
import math
import os
import sys

@dataclass(frozen=True)
class LocalModel:
    name: str
    label: str
    download_gb: float
    min_ram_gb: int
    description: str
    default: bool = False

RECOMMENDED_MODELS = (
    LocalModel('gemma4:12b', 'Gemma 4 12B (zalecany)', 8.0, 16,
               'Najlepszy wynik lokalny w próbie: 42 z 56 błędów w kontroli klinicznej i 96% poprawnych pól ekstrakcji.', True),
    LocalModel('gemma4:e4b', 'Gemma 4 E4B (dla słabszych komputerów)', 6.6, 12,
               'Dobra ekstrakcja (95,5% pól), ale znacznie słabsza kontrola kliniczna (19 z 56 błędów i wiele fałszywych alarmów).'),
    LocalModel('ornith-1.5:9b', 'Ornith 1.5 9B (model z zajęć)', 6.6, 12,
               'Model używany na zajęciach; w tej próbie Ollama znalazł 16 z 56 błędów i poprawnie wyodrębnił 92,8% pól.'),
)


def total_ram_gb():
    try:
        if sys.platform == 'win32':
            class MemoryStatus(ctypes.Structure):
                _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [
                    (name, ctypes.c_ulonglong) for name in ('total_phys', 'avail_phys', 'total_page',
                                                          'avail_page', 'total_virtual', 'avail_virtual', 'extended')]
            status = MemoryStatus()
            status.length = ctypes.sizeof(status)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return None
            size = status.total_phys
        elif sys.platform == 'darwin':
            size_value = ctypes.c_uint64()
            length = ctypes.c_size_t(ctypes.sizeof(size_value))
            if ctypes.CDLL(None).sysctlbyname(b'hw.memsize', ctypes.byref(size_value), ctypes.byref(length), None, 0):
                return None
            size = size_value.value
        else:
            size = os.sysconf('SC_PHYS_PAGES') * os.sysconf('SC_PAGE_SIZE')
        return size / 1024 ** 3 if size > 0 else None
    except (AttributeError, OSError, ValueError, TypeError, OverflowError):
        return None


def recommended_model(ram=None):
    return RECOMMENDED_MODELS[1] if ram is not None and ram < 16 else next(m for m in RECOMMENDED_MODELS if m.default)


def context_size(messages, max_tokens):
    prompt_chars = sum(len(message.get('content', '')) + len(message.get('role', '')) for message in messages)
    estimate = math.ceil(prompt_chars / 3) + max_tokens + 1024
    return min(32768, max(8192, math.ceil(estimate / 4096) * 4096))
