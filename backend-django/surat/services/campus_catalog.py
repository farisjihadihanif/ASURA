from typing import List, Dict, Any
# Surat yang disetujui Dekan. Selain ini, semua surat kampus disetujui Ketua Program Studi.
DEKAN_SURAT_CODES = {"SK-MK", "SK-UKT"}
CAMPUS_SURAT_CATALOG: List[Dict[str, Any]] = [
    # Grup Surat Keterangan
    {
        "kode_surat": "SK-MK",
        "nama_surat": "Surat Keterangan Masih Kuliah",
        "kategori": "Surat Keterangan",
        "is_auto_approval": False,
        "required_payload_fields": [
            {"field": "keperluan_surat", "label": "Keperluan Surat", "type": "string"},
        ],
    },
    {
        "kode_surat": "SK-UKT",
        "nama_surat": "Surat Keterangan Pembayaran UKT",
        "kategori": "Surat Keterangan",
        "is_auto_approval": False,
        "required_payload_fields": [
            {"field": "keperluan_surat", "label": "Keperluan Surat", "type": "string"},
        ],
    },
    {
        "kode_surat": "SK-BB",
        "nama_surat": "Surat Keterangan Berkelakuan Baik",
        "kategori": "Surat Keterangan",
        "is_auto_approval": False,
        "required_payload_fields": [
            {"field": "keperluan_surat", "label": "Keperluan Surat", "type": "string"},
        ],
    },
    {
        "kode_surat": "SK-HT",
        "nama_surat": "Surat Keterangan Habis Teori",
        "kategori": "Surat Keterangan",
        "is_auto_approval": False,
        "required_payload_fields": [
            {"field": "keperluan_surat", "label": "Keperluan Surat", "type": "string"},
        ],
    },
    {
        "kode_surat": "SK-TB",
        "nama_surat": "Surat Keterangan Tidak Sedang Menerima Beasiswa",
        "kategori": "Surat Keterangan",
        "is_auto_approval": False,
        "required_payload_fields": [
            {"field": "nama_beasiswa", "label": "Nama Beasiswa yang Dilamar", "type": "string"},
        ],
    },
    {
        "kode_surat": "SK-PS",
        "nama_surat": "Surat Keterangan Pindah Studi",
        "kategori": "Surat Keterangan",
        "is_auto_approval": False,
        "required_payload_fields": [
            {"field": "instansi_tujuan", "label": "Perguruan Tinggi / Prodi Tujuan", "type": "string"},
            {"field": "alasan_pindah", "label": "Alasan Pindah Studi", "type": "string"},
        ],
    },
    {
        "kode_surat": "SK-LL",
        "nama_surat": "Surat Keterangan Lulus",
        "kategori": "Surat Keterangan",
        "is_auto_approval": False,
        "required_payload_fields": [
            {"field": "tanggal_yudisium", "label": "Tanggal Yudisium / Sidang", "type": "date"},
            {"field": "keperluan_surat", "label": "Keperluan Surat", "type": "string"},
        ],
    },
    # Grup Surat Izin & Rekomendasi
    {
        "kode_surat": "SI-TL",
        "nama_surat": "Surat Permohonan Izin Tugas Lapangan",
        "kategori": "Surat Izin",
        "is_auto_approval": False,
        "required_payload_fields": [
            {"field": "instansi_tujuan", "label": "Instansi / Lokasi Tujuan", "type": "string"},
            {"field": "keperluan_surat", "label": "Topik / Mata Kuliah Tugas Lapangan", "type": "string"},
            {"field": "tanggal_mulai", "label": "Tanggal Pelaksanaan", "type": "date"},
        ],
    },
    {
        "kode_surat": "SI-PKL",
        "nama_surat": "Surat Permohonan Izin PPL/PLP/PKL/KP/PPS",
        "kategori": "Surat Izin",
        "is_auto_approval": False,
        "required_payload_fields": [
            {"field": "instansi_tujuan", "label": "Instansi / Lokasi Tujuan", "type": "string"},
            {"field": "tanggal_mulai", "label": "Tanggal Mulai", "type": "date"},
            {"field": "tanggal_selesai", "label": "Tanggal Selesai", "type": "date"},
        ],
    },
    {
        "kode_surat": "SI-MAG",
        "nama_surat": "Surat Permohonan Izin Magang",
        "kategori": "Surat Izin",
        "is_auto_approval": False,
        "required_payload_fields": [
            {"field": "instansi_tujuan", "label": "Instansi / Perusahaan Tujuan", "type": "string"},
            {"field": "posisi_magang", "label": "Posisi Magang", "type": "string"},
            {"field": "tanggal_mulai", "label": "Tanggal Mulai", "type": "date"},
            {"field": "tanggal_selesai", "label": "Tanggal Selesai", "type": "date"},
        ],
    },
    {
        "kode_surat": "SI-PMK",
        "nama_surat": "Surat Permohonan Izin Penelitian Mata Kuliah",
        "kategori": "Surat Izin",
        "is_auto_approval": False,
        "required_payload_fields": [
            {"field": "instansi_tujuan", "label": "Instansi / Objek Penelitian", "type": "string"},
            {"field": "mata_kuliah", "label": "Nama Mata Kuliah", "type": "string"},
            {"field": "judul_penelitian", "label": "Topik / Judul Penelitian", "type": "string"},
        ],
    },
    {
        "kode_surat": "SI-SP",
        "nama_surat": "Surat Permohonan Studi Pendahuluan",
        "kategori": "Surat Izin",
        "is_auto_approval": False,
        "required_payload_fields": [
            {"field": "instansi_tujuan", "label": "Instansi / Lokasi Tujuan", "type": "string"},
            {"field": "judul_penelitian", "label": "Topik Studi Pendahuluan", "type": "string"},
        ],
    },
    {
        "kode_surat": "SI-PTA",
        "nama_surat": "Surat Permohonan Izin Penelitian Tugas Akhir",
        "kategori": "Surat Izin",
        "is_auto_approval": False,
        "required_payload_fields": [
            {"field": "instansi_tujuan", "label": "Instansi / Lokasi Penelitian", "type": "string"},
            {"field": "judul_skripsi", "label": "Judul Skripsi / Tugas Akhir", "type": "string"},
        ],
    },
    {
        "kode_surat": "SR-PNL",
        "nama_surat": "Surat Permohonan Rekomendasi Penelitian",
        "kategori": "Surat Izin",
        "is_auto_approval": False,
        "required_payload_fields": [
            {"field": "instansi_tujuan", "label": "Instansi Tujuan Rekomendasi", "type": "string"},
            {"field": "judul_penelitian", "label": "Judul Penelitian", "type": "string"},
        ],
    },
    {
        "kode_surat": "SR-BEA",
        "nama_surat": "Surat Rekomendasi Beasiswa",
        "kategori": "Surat Rekomendasi",
        "is_auto_approval": False,
        "required_payload_fields": [
            {"field": "nama_beasiswa", "label": "Nama Program Beasiswa", "type": "string"},
            {"field": "instansi_tujuan", "label": "Penyelenggara Beasiswa", "type": "string"},
        ],
    },
    {
        "kode_surat": "CUSTOM-UMUM",
        "nama_surat": "Surat Permohonan / Keterangan Lainnya",
        "kategori": "Surat Umum",
        "is_auto_approval": False,
        "required_payload_fields": [
            {"field": "judul_surat", "label": "Jenis / Perihal Surat", "type": "string"},
            {"field": "instansi_tujuan", "label": "Tujuan / Penerima Surat", "type": "string"},
            {"field": "keperluan_surat", "label": "Keperluan / Detail Isi Surat", "type": "string"},
        ],
    },
]
CATALOG_CODES = [item["kode_surat"] for item in CAMPUS_SURAT_CATALOG]


def ensure_campus_surat_types() -> None:
    from surat.models import SuratType
    for item in CAMPUS_SURAT_CATALOG:
        SuratType.objects.update_or_create(
            kode_surat=item["kode_surat"],
            defaults={
                "nama_surat": item["nama_surat"],
                "kategori": item["kategori"],
                "is_auto_approval": item["is_auto_approval"],
                "required_payload_fields": item["required_payload_fields"],
            },
        )
