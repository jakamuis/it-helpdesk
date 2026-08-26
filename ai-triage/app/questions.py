from typing import Dict, Optional

from .schemas import QuestionKey


QUESTION_TEMPLATES: Dict[QuestionKey, str] = {
    "asset_id": "Mohon informasikan nomor aset perangkat yang bermasalah.",
    "site": "Kendala ini terjadi di lokasi atau site mana?",
    "symptom": "Gejala atau pesan error apa yang terlihat?",
    "printer_symptom": (
        "Gejala pada printernya seperti apa, misalnya kertas macet, offline, "
        "atau hasil cetak bermasalah?"
    ),
    "connection_type": "Koneksi yang digunakan Wi-Fi, LAN, atau VPN?",
    "affected_scope": "Apakah kendala ini hanya dialami Anda atau juga pengguna lain?",
    "affected_service": "Layanan atau aplikasi apa yang terdampak?",
    "business_impact": "Apa dampak kendala ini terhadap pekerjaan atau operasional?",
}

FALLBACK_QUESTION = (
    "Baik, informasi Anda sudah kami terima. Mohon jelaskan sedikit lebih detail "
    "kendala yang terjadi agar dapat kami teruskan ke tim IT."
)


def render_question(question_key: Optional[QuestionKey]) -> Optional[str]:
    if question_key is None:
        return None
    return QUESTION_TEMPLATES[question_key]
