import os
import re
import shutil
from pathlib import Path

DST_BACKEND = Path(__file__).resolve().parent

SEARCH_BASES = [
    Path(r"D:\coolyeah\Semester 7\perancangan komputasi interaktif\project\auto-surat-backend\backend-django"),
    Path(r"D:\coolyeah\Semester 7\Perancangan Komputasi Interaktif\auto-surat-backend\backend-django"),
]


def find_source_backend() -> Path:
    for candidate in SEARCH_BASES:
        if (candidate / "manage.py").exists() and (candidate / "accounts").exists():
            return candidate
    coolyeah = Path(r"D:\coolyeah")
    if coolyeah.exists():
        for root, dirs, files in os.walk(coolyeah):
            p = Path(root)
            if "ASURA" in p.parts or "node_modules" in p.parts or ".venv" in p.parts:
                dirs[:] = []
                continue
            if "manage.py" in files and (p / "accounts").exists() and (p / "core").exists():
                return p
    raise FileNotFoundError("Folder sumber backend-django tidak ditemukan di D:\\coolyeah.")


def patch_copied_chat_workflow():
    cw_path = DST_BACKEND / "surat" / "services" / "chat_workflow.py"
    if not cw_path.exists():
        return
    cw_code = cw_path.read_text(encoding="utf-8")
    old_block_pattern = re.compile(
        r"    if main_slots_complete:\n.*?(?=\n    # 1\. GUNAKAN AI / EXTRACTOR)",
        re.DOTALL,
    )
    new_main_complete_block = '''    if main_slots_complete:
        slots_summary = "\\n".join(
            f"- **{str(item.get('label') or item.get('field')).strip()}**: {str(current_slots.get(item.get('field'), '-')).strip()}"
            for item in required_fields
        )
        return (
            f"Seluruh data wajib untuk **{surat_type.nama_surat}** sudah lengkap:\\n\\n"
            f"{slots_summary}\\n\\n"
            f"Silakan klik tombol **Ajukan Surat ke Dosen** di bawah untuk mengirim draf ke antrean persetujuan dosen."
        )
'''
    cw_code = old_block_pattern.sub(new_main_complete_block, cw_code, count=1)
    cw_code = cw_code.replace(
        "    return format_state3_complete_summary(slots_summary)",
        '''    summary_lines = "\\n".join(f"- **{s['label']}**: {s['value']}" for s in slots_summary)
    return (
        f"Terima kasih, seluruh informasi wajib untuk **{surat_type.nama_surat}** telah terkumpul:\\n\\n"
        f"{summary_lines}\\n\\n"
        f"Silakan klik tombol **Ajukan Surat ke Dosen** di bawah agar draf surat segera disusun dan dikirim ke dosen untuk di-ACC."
    )''',
    )
    cw_path.write_text(cw_code, encoding="utf-8")


def sync_missing_files():
    if not ((DST_BACKEND / "manage.py").exists() and (DST_BACKEND / "accounts").exists()):
        src_backend = find_source_backend()
        print(f"[ASURA] Menyalin modul inti dari {src_backend} ke {DST_BACKEND}...")
        skip_names = {"__pycache__", ".venv", "venv", "media", "staticfiles"}
        for root, dirs, files in os.walk(src_backend):
            dirs[:] = [d for d in dirs if d not in skip_names]
            rel_dir = Path(root).relative_to(src_backend)
            for fname in files:
                if fname.endswith((".pyc", ".sqlite3")) or fname.startswith("db.sqlite3"):
                    continue
                src_file = Path(root) / fname
                dst_file = DST_BACKEND / rel_dir / fname
                if not dst_file.exists():
                    dst_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_file, dst_file)

        for env_candidate in [src_backend / ".env", src_backend.parent / ".env"]:
            if env_candidate.exists() and not (DST_BACKEND / ".env").exists():
                shutil.copy2(env_candidate, DST_BACKEND / ".env")
                break

    patch_copied_chat_workflow()


if __name__ == "__main__":
    sync_missing_files()