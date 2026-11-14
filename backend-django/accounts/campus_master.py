"""Master data kampus (dummy) menyerupai data terintegrasi autosurat.uin-suka.ac.id.

Format NIM (11 digit):  AA SS FF PPP UU
  AA  = 2 digit angkatan (23 = masuk 2023)
  SS  = 2 digit semester masuk (10 = ganjil, 20 = genap)
  FF  = 2 digit kode fakultas (60 Teknik, 70 Sains dan Teknologi, 80 Kedokteran)
  PPP = 3 digit kode program studi (500 = prodi pertama, 501 kedua, dst. di tiap fakultas)
  UU  = 2 digit urutan (berdasarkan urutan pembayaran UKT)
"""
from datetime import datetime

SEMESTER_CODE = {"GANJIL": "10", "GENAP": "20"}

# kode fakultas -> (id, nama, [(kode_prodi, id_prodi, nama_prodi, singkatan)])
FACULTIES = [
    ("60", "FT", "Teknik", [
        ("500", "FT-TIF", "Teknik Informatika", "TF"),
        ("501", "FT-SP", "Teknik Sipil", "SP"),
        ("502", "FT-MS", "Teknik Mesin", "MS"),
        ("503", "FT-EL", "Teknik Elektro", "EL"),
        ("504", "FT-IN", "Teknik Industri", "IN"),
        ("505", "FT-KI", "Teknik Kimia", "KI"),
        ("506", "FT-AR", "Arsitektur", "AR"),
        ("507", "FT-LG", "Teknik Lingkungan", "LG"),
    ]),
    ("70", "FST", "Sains dan Teknologi", [
        ("500", "FST-IF", "Informatika", "IF"),
        ("501", "FST-MT", "Matematika", "MT"),
        ("502", "FST-FS", "Fisika", "FS"),
        ("503", "FST-KM", "Kimia", "KM"),
        ("504", "FST-BI", "Biologi", "BI"),
        ("505", "FST-TI", "Teknik Industri", "TI"),
        ("506", "FST-TE", "Teknik Elektro", "TE"),
        ("507", "FST-AG", "Agroteknologi", "AG"),
    ]),
    ("80", "FK", "Kedokteran", [
        ("500", "FK-PD", "Pendidikan Dokter", "PD"),
        ("501", "FK-KG", "Kedokteran Gigi", "KG"),
        ("502", "FK-FM", "Farmasi", "FM"),
        ("503", "FK-KP", "Keperawatan", "KP"),
        ("504", "FK-KB", "Kebidanan", "KB"),
        ("505", "FK-GZ", "Gizi", "GZ"),
        ("506", "FK-KS", "Kesehatan Masyarakat", "KS"),
        ("507", "FK-RM", "Rekam Medis dan Informasi Kesehatan", "RM"),
    ]),
]

# Mata kuliah umum per semester (1 per semester)
SHARED_COURSES = [
    "Pendidikan Agama Islam", "Bahasa Indonesia", "Pendidikan Pancasila dan Kewarganegaraan",
    "Bahasa Inggris Akademik", "Kewirausahaan", "Etika Profesi dan Metodologi Penelitian",
    "Kuliah Kerja Nyata (KKN)", "Skripsi",
]

# 16 mata kuliah inti per prodi: 2 per semester (semester 1..8)
CORE_COURSES = {
    "FST-IF": ["Algoritma dan Pemrograman", "Matematika Diskrit", "Struktur Data", "Logika Informatika", "Basis Data", "Organisasi dan Arsitektur Komputer", "Pemrograman Berorientasi Objek", "Sistem Operasi", "Jaringan Komputer", "Rekayasa Perangkat Lunak", "Kecerdasan Buatan", "Pemrograman Web", "Pembelajaran Mesin", "Keamanan Informasi", "Pengembangan Aplikasi Mobile", "Manajemen Proyek TI"],
    "FST-MT": ["Kalkulus I", "Logika dan Himpunan", "Kalkulus II", "Aljabar Linear Elementer", "Statistika Dasar", "Persamaan Diferensial Biasa", "Analisis Real I", "Struktur Aljabar", "Analisis Real II", "Pemrograman Komputer", "Teori Peluang", "Metode Numerik", "Riset Operasi", "Matematika Keuangan", "Pemodelan Matematika", "Topologi"],
    "FST-FS": ["Fisika Dasar I", "Kalkulus Fisika", "Fisika Dasar II", "Mekanika", "Gelombang dan Optik", "Termodinamika", "Listrik dan Magnet", "Fisika Matematika", "Mekanika Kuantum", "Fisika Zat Padat", "Fisika Inti", "Elektronika Dasar", "Fisika Komputasi", "Fisika Material", "Instrumentasi Fisika", "Astrofisika"],
    "FST-KM": ["Kimia Dasar I", "Kalkulus Kimia", "Kimia Dasar II", "Kimia Organik I", "Kimia Anorganik I", "Kimia Analitik I", "Kimia Fisika I", "Kimia Organik II", "Kimia Analitik Instrumen", "Biokimia", "Kimia Polimer", "Kimia Lingkungan", "Kimia Komputasi", "Elektrokimia", "Kimia Material", "Kimia Bahan Alam"],
    "FST-BI": ["Biologi Sel", "Kimia Dasar untuk Biologi", "Botani Tumbuhan Rendah", "Zoologi Invertebrata", "Genetika", "Mikrobiologi", "Fisiologi Tumbuhan", "Ekologi", "Biologi Molekuler", "Biostatistika", "Bioteknologi", "Taksonomi Tumbuhan", "Fisiologi Hewan", "Biologi Konservasi", "Mikrobiologi Industri", "Bioinformatika"],
    "FST-TI": ["Pengantar Teknik Industri", "Kalkulus untuk Teknik", "Fisika Teknik", "Statistika Industri", "Gambar Teknik", "Proses Manufaktur", "Ergonomi", "Penelitian Operasional", "Perancangan Tata Letak Fasilitas", "Pengendalian Kualitas", "Perencanaan dan Pengendalian Produksi", "Simulasi Sistem", "Manajemen Rantai Pasok", "Sistem Manajemen Mutu", "Perancangan Produk", "Ekonomi Teknik"],
    "FST-TE": ["Rangkaian Listrik I", "Kalkulus untuk Teknik", "Rangkaian Listrik II", "Elektronika Analog", "Sistem Digital", "Medan Elektromagnetik", "Sinyal dan Sistem", "Mesin Listrik", "Sistem Kendali", "Mikroprosesor", "Elektronika Daya", "Sistem Tenaga Listrik", "Pengolahan Sinyal Digital", "Telekomunikasi", "Instrumentasi dan Pengukuran", "Energi Terbarukan"],
    "FST-AG": ["Pengantar Agroteknologi", "Biologi Pertanian", "Kimia Tanah", "Dasar Budidaya Tanaman", "Fisiologi Tumbuhan Budidaya", "Ilmu Tanah", "Hama dan Penyakit Tanaman", "Agroklimatologi", "Teknologi Benih", "Pemuliaan Tanaman", "Pertanian Berkelanjutan", "Hortikultura", "Teknologi Pascapanen", "Agribisnis", "Pertanian Presisi", "Bioteknologi Pertanian"],
    "FT-TIF": ["Dasar Pemrograman", "Matematika Teknik", "Algoritma dan Struktur Data", "Sistem Digital", "Basis Data", "Pemrograman Berorientasi Objek", "Jaringan Komputer", "Sistem Operasi", "Rekayasa Perangkat Lunak", "Interaksi Manusia dan Komputer", "Kecerdasan Buatan", "Komputasi Awan", "Data Mining", "Keamanan Siber", "Pemrograman Mobile", "Tata Kelola TI"],
    "FT-SP": ["Mekanika Teknik I", "Gambar Teknik Sipil", "Mekanika Teknik II", "Ilmu Ukur Tanah", "Mekanika Bahan", "Mekanika Fluida", "Teknologi Beton", "Mekanika Tanah", "Analisis Struktur", "Hidrolika", "Struktur Beton Bertulang", "Teknik Pondasi", "Rekayasa Jalan Raya", "Struktur Baja", "Manajemen Konstruksi", "Rekayasa Irigasi"],
    "FT-MS": ["Mekanika Teknik", "Gambar Mesin", "Termodinamika Teknik", "Material Teknik", "Mekanika Fluida", "Proses Manufaktur", "Elemen Mesin", "Perpindahan Panas", "Mesin Konversi Energi", "Getaran Mekanik", "Sistem Kontrol", "Metrologi Industri", "Mekatronika", "Teknik Pendingin", "Perancangan Mesin", "CAD/CAM"],
    "FT-EL": ["Rangkaian Listrik", "Matematika Teknik", "Elektronika Dasar", "Sistem Digital", "Medan Elektromagnetik", "Sinyal dan Sistem", "Mesin Listrik", "Sistem Kendali", "Mikrokontroler", "Elektronika Daya", "Transmisi Tenaga Listrik", "Pengolahan Sinyal", "Sistem Komunikasi", "Instrumentasi", "Distribusi Tenaga Listrik", "Energi Baru Terbarukan"],
    "FT-IN": ["Pengantar Teknik Industri", "Kalkulus Teknik", "Statistika Industri", "Gambar Teknik", "Ergonomi dan Perancangan Kerja", "Proses Produksi", "Riset Operasi", "Perancangan Fasilitas", "Pengendalian Kualitas", "Perencanaan Produksi", "Simulasi Sistem", "Manajemen Logistik", "Manajemen Mutu Terpadu", "Perancangan Produk", "Keselamatan dan Kesehatan Kerja", "Ekonomi Teknik"],
    "FT-KI": ["Pengantar Teknik Kimia", "Kimia Dasar", "Neraca Massa dan Energi", "Kimia Organik", "Termodinamika Kimia", "Mekanika Fluida", "Perpindahan Panas", "Operasi Teknik Kimia I", "Kinetika Reaksi", "Operasi Teknik Kimia II", "Teknik Reaksi Kimia", "Pengendalian Proses", "Perancangan Pabrik", "Teknologi Bioproses", "Teknik Pengolahan Limbah", "Teknologi Polimer"],
    "FT-AR": ["Dasar Perancangan Arsitektur", "Gambar Arsitektur", "Sejarah Arsitektur", "Teori Arsitektur", "Struktur dan Konstruksi Bangunan", "Studio Perancangan I", "Utilitas Bangunan", "Studio Perancangan II", "Arsitektur Tropis", "Perancangan Kota", "Studio Perancangan III", "Arsitektur Islam", "Konservasi Bangunan", "Manajemen Proyek Arsitektur", "Studio Perancangan IV", "Arsitektur Berkelanjutan"],
    "FT-LG": ["Pengantar Teknik Lingkungan", "Kimia Lingkungan", "Mikrobiologi Lingkungan", "Mekanika Fluida", "Hidrologi", "Pengelolaan Air Minum", "Pengelolaan Air Limbah", "Pencemaran Udara", "Pengelolaan Persampahan", "Analisis Mengenai Dampak Lingkungan", "Pemodelan Lingkungan", "Teknologi Pengolahan Limbah B3", "Sistem Informasi Geografis", "Audit Lingkungan", "Perencanaan Lingkungan", "Ekotoksikologi"],
    "FK-PD": ["Biologi Sel dan Molekuler", "Anatomi Dasar", "Fisiologi Dasar", "Biokimia Medik", "Sistem Muskuloskeletal", "Sistem Kardiovaskular", "Sistem Respirasi", "Sistem Pencernaan", "Mikrobiologi Kedokteran", "Farmakologi Dasar", "Patologi Anatomi", "Ilmu Penyakit Dalam", "Ilmu Kesehatan Anak", "Ilmu Bedah", "Kedokteran Keluarga", "Etika dan Hukum Kedokteran"],
    "FK-KG": ["Anatomi Gigi dan Mulut", "Biologi Oral", "Fisiologi Oral", "Biokimia Oral", "Material Kedokteran Gigi", "Histologi Oral", "Ilmu Penyakit Mulut", "Radiologi Dental", "Konservasi Gigi", "Periodontologi", "Bedah Mulut", "Ortodonsia", "Prostodonsia", "Pedodonsia", "Kesehatan Gigi Masyarakat", "Etika dan Hukum Kedokteran Gigi"],
    "FK-FM": ["Kimia Farmasi Dasar", "Biologi Farmasi", "Fisika Farmasi", "Anatomi Fisiologi Manusia", "Kimia Organik Farmasi", "Farmakognosi", "Farmasetika Dasar", "Kimia Analisis Farmasi", "Farmakologi", "Teknologi Sediaan Padat", "Teknologi Sediaan Cair dan Semi Padat", "Farmakokinetika", "Kimia Medisinal", "Farmasi Klinik", "Farmasi Industri", "Regulasi dan Etika Farmasi"],
    "FK-KP": ["Konsep Dasar Keperawatan", "Anatomi dan Fisiologi", "Keterampilan Dasar Keperawatan", "Farmakologi Keperawatan", "Keperawatan Medikal Bedah I", "Keperawatan Maternitas", "Keperawatan Anak", "Keperawatan Medikal Bedah II", "Keperawatan Jiwa", "Keperawatan Gawat Darurat", "Keperawatan Komunitas", "Keperawatan Gerontik", "Manajemen Keperawatan", "Keperawatan Keluarga", "Riset Keperawatan", "Praktik Klinik Keperawatan"],
    "FK-KB": ["Anatomi dan Fisiologi Reproduksi", "Konsep Kebidanan", "Asuhan Kehamilan", "Biologi Perkembangan", "Asuhan Persalinan", "Asuhan Nifas dan Menyusui", "Asuhan Bayi Baru Lahir", "Kesehatan Reproduksi", "Keluarga Berencana", "Kebidanan Komunitas", "Patologi Kebidanan", "Farmakologi Kebidanan", "Asuhan Neonatus Risiko Tinggi", "Manajemen Kebidanan", "Riset Kebidanan", "Praktik Klinik Kebidanan"],
    "FK-GZ": ["Ilmu Gizi Dasar", "Anatomi dan Fisiologi", "Biokimia Gizi", "Ilmu Pangan", "Gizi dalam Daur Kehidupan", "Mikrobiologi Pangan", "Penilaian Status Gizi", "Dietetik Dasar", "Gizi Masyarakat", "Teknologi Pangan", "Dietetik Penyakit Degeneratif", "Gizi Olahraga", "Manajemen Penyelenggaraan Makanan", "Gizi Klinik", "Epidemiologi Gizi", "Konseling Gizi"],
    "FK-KS": ["Pengantar Kesehatan Masyarakat", "Biologi untuk Kesehatan", "Ilmu Perilaku Kesehatan", "Biostatistika", "Epidemiologi Dasar", "Kesehatan Lingkungan", "Administrasi Kebijakan Kesehatan", "Promosi Kesehatan", "Epidemiologi Penyakit Menular", "Kesehatan dan Keselamatan Kerja", "Gizi Kesehatan Masyarakat", "Surveilans Kesehatan", "Manajemen Rumah Sakit", "Ekonomi Kesehatan", "Kesehatan Reproduksi", "Penelitian Kesehatan"],
    "FK-RM": ["Pengantar Rekam Medis", "Anatomi dan Fisiologi", "Terminologi Medis", "Manajemen Data Kesehatan", "Klasifikasi dan Kodifikasi Penyakit I", "Hukum Kesehatan", "Statistik Kesehatan", "Klasifikasi dan Kodifikasi Penyakit II", "Sistem Informasi Kesehatan", "Manajemen Pelayanan Rekam Medis", "Epidemiologi", "Manajemen Mutu Pelayanan", "Informatika Kesehatan", "Pelaporan Rumah Sakit", "Etika dan Keamanan Informasi Kesehatan", "Rekam Medis Elektronik"],
}

FIRST_NAMES = ["Ahmad", "Budi", "Citra", "Dewi", "Eko", "Fajar", "Gita", "Hana", "Indra", "Joko", "Kartika", "Lukman", "Maya", "Nadia", "Omar", "Putri", "Qori", "Rizky", "Siti", "Taufik", "Umar", "Vina", "Wahyu", "Yusuf", "Zahra", "Aulia", "Bagas", "Cahya", "Dimas", "Elsa", "Farhan", "Gilang", "Hafiz", "Intan", "Jihan", "Khalid", "Laila", "Mirza", "Nabila", "Oki"]
LAST_NAMES = ["Pratama", "Santoso", "Wijaya", "Rahman", "Hidayat", "Saputra", "Nugroho", "Lestari", "Kusuma", "Permana", "Firmansyah", "Ramadhan", "Suryani", "Hakim", "Setiawan", "Maulana", "Anggraini", "Purnomo", "Fauzi", "Syahputra", "Utami", "Wibowo", "Amalia", "Kurniawan", "Hasanah"]
TITLES = ["Dr.", "Prof. Dr.", "Dr.", "Dr.", ""]
DEGREES = ["M.Kom.", "M.T.", "M.Sc.", "M.Si.", "M.Pd.", "M.Kes.", "Ph.D."]

LECTURERS_PER_PRODI = 5
JOEL_NIP = "198001012005011001"  # Dekan Fakultas Teknik (akun demo lama dipertahankan)
FARIS_NIM = "23106050031"

ANGKATAN_LIST = [23, 24, 25, 26]


def academic_year_and_semester(angkatan_yy: int, now=None):
    now = now or datetime.now()
    y, m = now.year, now.month
    tahun_akademik = f"{y}/{y + 1}" if m >= 8 else f"{y - 1}/{y}"
    tahun_masuk = 2000 + angkatan_yy
    semester = (y - tahun_masuk) * 2 + (1 if m >= 8 else 0)
    return tahun_akademik, tahun_masuk, max(1, min(semester, 14))


def build_nim(angkatan_yy: int, semester_masuk: str, kode_fakultas: str, kode_prodi: str, urut: int) -> str:
    return f"{angkatan_yy:02d}{SEMESTER_CODE[semester_masuk]}{kode_fakultas}{kode_prodi}{urut:02d}"


def parse_nim(nim: str):
    """Pecah NIM 11 digit -> dict (angkatan, semester_masuk, fakultas, prodi, urut) atau None."""
    s = str(nim or "").strip()
    if len(s) != 11 or not s.isdigit():
        return None
    return {
        "angkatan": int(s[0:2]),
        "semester_masuk": "GANJIL" if s[2:4] == "10" else ("GENAP" if s[2:4] == "20" else None),
        "kode_fakultas": s[4:6],
        "kode_prodi": s[6:9],
        "urut": int(s[9:11]),
    }


def person_name(idx: int, salt: int = 0) -> str:
    f = FIRST_NAMES[(idx * 7 + salt) % len(FIRST_NAMES)]
    l = LAST_NAMES[(idx * 11 + salt * 3) % len(LAST_NAMES)]
    return f"{f} {l}"


def lecturer_nip(idx: int) -> str:
    birth_year = 1968 + (idx * 5) % 22
    month = 1 + (idx * 3) % 12
    day = 1 + (idx * 7) % 28
    tmt_year = birth_year + 27 + (idx % 3)
    gender = 1 + idx % 2
    return f"{birth_year}{month:02d}{day:02d}{tmt_year}{1 + (idx % 12):02d}{gender}{(idx % 900) + 100:03d}"
