from django.test import TestCase
from unittest.mock import patch, MagicMock
from rest_framework.test import APIRequestFactory, force_authenticate
from accounts.models import User, Faculty, Department, Lecturer, Student
from surat.models import SuratType, SuratRequest, SuratApproval, SuratAuditLog, SuratStatus, ChatThread, ChatMessage
from surat.serializers import SuratRequestDetailSerializer
from surat.agents.execution_tools import SuratExecutionTools, ExecutionPipelineResult
from surat.services.workflow_service import _execute_final_issuance_worker
from surat.views import ChatSessionMessageAPIView
from surat.services.session_manager import AutoSuratSessionManager


class SuratArchitecturalFixesTestCase(TestCase):
    """
    Test suite komprehensif untuk memvalidasi implementasi perbaikan temuan 4, 5, dan 6:
    - Temuan 4: Field chosen_destination & target_destination_address pada SuratRequestDetailSerializer
    - Temuan 5: Delegasi eksekusi pasca-approval ke SuratExecutionTools (eliminasi duplikasi logika)
    - Temuan 6: Resolusi template_path dinamis tanpa penimpaan hardcoded
    """

    def setUp(self):
        # 1. Setup User & Organisasi
        self.user_lec = User.objects.create(
            id="u-lec-test",
            nama="Dr. Budi Santoso, M.Kom.",
            nip_nim="198001012005011001",
            role="LECTURER",
            password="password123",
        )
        self.user_mhs = User.objects.create(
            id="u-mhs-test",
            nama="Ahmad Bintang",
            nip_nim="210001001",
            role="STUDENT",
            password="password123",
        )

        self.fakultas = Faculty.objects.create(
            id="FT-TEST",
            nama_fakultas="Fakultas Teknik",
        )
        self.prodi = Department.objects.create(
            id="INF-TEST",
            fakultas=self.fakultas,
            nama_prodi="Informatika",
        )

        self.lecturer = Lecturer.objects.create(
            id="l-test-01",
            user=self.user_lec,
            fakultas=self.fakultas,
            prodi=self.prodi,
            jabatan_struktural=["Dekan Fakultas Teknik"],
        )
        self.fakultas.dekan = self.lecturer
        self.fakultas.save()

        self.student = Student.objects.create(
            nim="210001001",
            user=self.user_mhs,
            fakultas=self.fakultas,
            prodi=self.prodi,
            semester_aktif=7,
            tahun_akademik="2026/2027",
            tahun_masuk=2021,
        )

        # 2. Setup SuratType
        self.surat_type_custom = SuratType.objects.create(
            kode_surat="SR-MAG",
            nama_surat="Surat Rekomendasi Magang",
            kategori="Rekomendasi",
            is_auto_approval=False,
            template_path="surat/sr.mag.html",
        )

        self.surat_type_empty = SuratType.objects.create(
            kode_surat="SK-KUL",
            nama_surat="Surat Keterangan Aktif Kuliah",
            kategori="Keterangan",
            is_auto_approval=True,
            template_path="",
        )

        # 3. Setup SuratRequest
        self.surat_req = SuratRequest.objects.create(
            student=self.student,
            kode_surat=self.surat_type_custom,
            status=SuratStatus.PENDING_APPROVAL,
            chosen_destination="email",
            target_destination_address="bintang@student.ac.id",
            payload_data={
                "instansi_tujuan": "PT Telkom Indonesia",
                "posisi_dilamar": "Backend Engineer",
            },
            ai_original_draft="Draf awal permohonan magang mahasiswa.",
            final_approved_content="Naskah surat rekomendasi magang yang disetujui dosen.",
        )

    def test_temuan4_serializer_exposes_chosen_destination_and_address(self):
        """
        Validasi Temuan 4:
        SuratRequestDetailSerializer wajib menyertakan 'chosen_destination'
        dan 'target_destination_address' pada output JSON ke frontend.
        """
        serializer = SuratRequestDetailSerializer(self.surat_req)
        data = serializer.data

        self.assertIn("chosen_destination", data)
        self.assertIn("target_destination_address", data)
        self.assertEqual(data["chosen_destination"], "email")
        self.assertEqual(data["target_destination_address"], "bintang@student.ac.id")

    def test_temuan6_resolve_template_path_existing_template(self):
        """
        Validasi Temuan 6:
        Template khusus yang ada di disk ('surat/sr.mag.html') dipertahankan.
        """
        tools = SuratExecutionTools()
        resolved = tools.resolve_template_path(self.surat_req)
        self.assertEqual(resolved, "surat/sr.mag.html")

    def test_temuan6_resolve_template_path_with_templates_prefix(self):
        """
        Validasi Temuan 6:
        Prefiks 'templates/' yang tercatat di database otomatis dibersihkan.
        """
        self.surat_type_custom.template_path = "templates/surat/sr.mag.html"
        self.surat_type_custom.save()
        self.surat_req.refresh_from_db()

        tools = SuratExecutionTools()
        resolved = tools.resolve_template_path(self.surat_req)
        self.assertEqual(resolved, "surat/sr.mag.html")

    def test_temuan6_resolve_template_path_fallback_when_empty_or_missing(self):
        """
        Validasi Temuan 6:
        Jika template_path kosong atau merujuk berkas yang tidak ada,
        otomatis dialihkan ke 'kerangka-surat/base_surat.html'.
        """
        tools = SuratExecutionTools()

        # Kasus 1: template_path kosong
        self.surat_req.kode_surat = self.surat_type_empty
        resolved_empty = tools.resolve_template_path(self.surat_req)
        self.assertEqual(resolved_empty, "kerangka-surat/base_surat.html")

        # Kasus 2: template_path tidak ada di disk
        self.surat_type_empty.template_path = "surat/file_tidak_ada.html"
        self.surat_req.kode_surat = self.surat_type_empty
        resolved_missing = tools.resolve_template_path(self.surat_req)
        self.assertEqual(resolved_missing, "kerangka-surat/base_surat.html")

    @patch("surat.services.workflow_service.close_old_connections")
    @patch("surat.services.workflow_service._execute_distribution_worker")
    @patch.object(SuratExecutionTools, "execute_approval_pipeline")
    def test_temuan5_workflow_worker_delegates_to_execution_tools(
        self,
        mock_pipeline,
        mock_distribution,
        mock_close_conns,
    ):
        """
        Validasi Temuan 5 & 6:
        _execute_final_issuance_worker mendelegasikan eksekusi penerbitan
        dokumen ke SuratExecutionTools.execute_approval_pipeline tanpa menduplikasi
        logika WeasyPrint/Cloudinary dan TANPA menimpa kode_surat.template_path.
        """
        mock_pipeline.return_value = ExecutionPipelineResult(
            surat_request_id=self.surat_req.id,
            nomor_surat_resmi="001/UN.1/FT/2026",
            file_pdf_url="https://res.cloudinary.com/demo/image/upload/v1/surat.pdf",
            qr_code_url="https://auto-surat-backend.onrender.com/surat/verify/token-123/",
            tte_token="token-123",
            hash_document="hash-sha256-abc",
            final_status="SENT",
            final_approved_content=self.surat_req.final_approved_content,
        )

        original_template_path = self.surat_req.kode_surat.template_path

        _execute_final_issuance_worker(
            surat_request_id=self.surat_req.id,
            signer_lecturer_id=self.lecturer.id,
            final_status="SENT",
        )

        # 1. Pastikan execute_approval_pipeline dipanggil sekali dengan parameter yang tepat
        mock_pipeline.assert_called_once()
        call_kwargs = mock_pipeline.call_args.kwargs
        self.assertEqual(call_kwargs["surat_request"].id, self.surat_req.id)
        self.assertEqual(call_kwargs["signer"].id, self.lecturer.id)
        self.assertEqual(call_kwargs["final_status"], "SENT")
        self.assertEqual(
            call_kwargs["final_approved_content"],
            self.surat_req.final_approved_content,
        )

        # 2. Pastikan template_path pada model kode_surat TIDAK DITIMPA menjadi 'base_surat.html'
        self.surat_req.kode_surat.refresh_from_db()
        self.assertEqual(self.surat_req.kode_surat.template_path, original_template_path)

        # 3. Pastikan _execute_distribution_worker dipanggil
        mock_distribution.assert_called_once_with(self.surat_req.id)

    @patch("surat.agents.execution_tools._resolve_pdf_fn")
    @patch("surat.agents.execution_tools._resolve_tte_fn")
    @patch("surat.agents.execution_tools._resolve_number_fn")
    def test_pipeline_execution_real_integration(
        self,
        mock_number_fn,
        mock_tte_fn,
        mock_pdf_fn,
    ):
        """
        Validasi alur integrasi end-to-end execute_approval_pipeline:
        - Pembuatan nomor surat resmi
        - Pembuatan TTE & QR Code
        - Render context (approvals, QR base64, signer)
        - Pembaruan status SuratRequest menjadi SENT
        - Pencatatan SuratAuditLog FIN_01
        """
        mock_number_fn.return_value = lambda *args, **kwargs: "B/100/FT/2026"
        mock_tte_fn.return_value = lambda *args, **kwargs: {
            "token": "token-test-xyz",
            "hash_document": "hash-sha256-xyz",
            "qr_code_url": "https://auto-surat.test/verify/xyz/",
        }
        mock_pdf_fn.return_value = lambda tmpl, ctx: "https://cloudinary.test/surat_resmi.pdf"

        # Buat riwayat SuratApproval
        SuratApproval.objects.create(
            surat_request=self.surat_req,
            approver=self.lecturer,
            step_order=1,
            status="APPROVED",
            catatan="Disetujui Dekan",
        )

        tools = SuratExecutionTools()
        result = tools.execute_approval_pipeline(
            surat_request=self.surat_req,
            signer=self.lecturer,
            final_approved_content="Naskah Surat Resmi Terverifikasi",
            final_status="SENT",
        )

        self.assertEqual(result.nomor_surat_resmi, "B/100/FT/2026")
        self.assertEqual(result.file_pdf_url, "https://cloudinary.test/surat_resmi.pdf")
        self.assertEqual(result.final_status, "SENT")

        # Verifikasi data tersimpan di database
        self.surat_req.refresh_from_db()
        self.assertEqual(self.surat_req.nomor_surat_resmi, "B/100/FT/2026")
        self.assertEqual(self.surat_req.file_pdf_url, "https://cloudinary.test/surat_resmi.pdf")
        self.assertEqual(self.surat_req.status, "SENT")
        self.assertEqual(self.surat_req.final_approved_content, "Naskah Surat Resmi Terverifikasi")

        # Verifikasi SuratAuditLog FIN_01 tercatat
        audit_log = SuratAuditLog.objects.filter(
            surat_request=self.surat_req,
            action_id="FIN_01",
        ).first()
        self.assertIsNotNone(audit_log)
        self.assertIn("SENT", audit_log.action)

    def test_pdf_context_has_base64_qr_and_approvals(self):
        """
        Validasi pembentukan context data untuk template HTML:
        - qr_code_url memuat data-uri base64 PNG yang valid
        - qr_verification_code memuat tautan publik verifikasi
        - approvals memuat daftar terstruktur
        - tanggal_terbit dan tanggal_surat tersedia
        """
        tools = SuratExecutionTools()
        context = tools.build_pdf_template_context(
            surat_request=self.surat_req,
            nomor_surat="B/101/FT/2026",
            qr_code_url="https://auto-surat.test/verify/token-abc/",
            final_approved_content="Isi naskah resmi",
            signer=self.lecturer,
        )

        self.assertIn("qr_code_url", context)
        self.assertTrue(context["qr_code_url"].startswith("data:image/png;base64,"))
        self.assertEqual(context["qr_verification_code"], "https://auto-surat.test/verify/token-abc/")
        self.assertIn("approvals", context)
        self.assertIsInstance(context["approvals"], list)
        self.assertGreaterEqual(len(context["approvals"]), 1)
        self.assertIn("tanggal_terbit", context)
        self.assertIn("tanggal_surat", context)
        self.assertEqual(context["nomor_surat"], "B/101/FT/2026")


class ChatSessionContractAndPersistenceTestCase(TestCase):
    """
    Test suite untuk memvalidasi kontrak API dan persistensi sesi chat:
    1. ChatMessage tersimpan ke PostgreSQL tanpa galat konstrain sender_type
    2. Endpoint POST /api/surat/chat/<thread_id>/ mengembalikan is_ready_to_draft: True dan intent saat slot lengkap
    3. Endpoint GET /api/surat/chat/<thread_id>/ mengembalikan riwayat pesan dan snapshot sesi yang utuh
    """

    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User.objects.create(
            id="u-std-contract-test",
            nama="Julian Sanchez",
            nip_nim="INF24001",
            role="STUDENT",
            password="password123",
        )
        self.user.is_authenticated = True
        self.surat_type = SuratType.objects.create(
            kode_surat="SR-MAG",
            nama_surat="Surat Rekomendasi Magang",
            required_payload_fields=[
                {"field": "instansi_tujuan", "label": "Instansi Tujuan"},
                {"field": "posisi_dilamar", "label": "Posisi Dilamar"},
            ],
        )
        self.thread = ChatThread.objects.create(
            user=self.user,
            title="Sesi Permohonan Surat Magang",
            document_type="SR-MAG",
            status=ChatThread.ThreadStatus.ACTIVE,
        )

    def test_chat_message_persistence_without_constraint_error(self):
        """Memastikan pesan chat dapat disimpan ke PostgreSQL tanpa galat pada kolom sender_type."""
        msg = ChatMessage.objects.create(
            thread=self.thread,
            sender="user",
            message="Saya ingin magang di PT Telekomunikasi.",
            slots_snapshot={"instansi_tujuan": "PT Telekomunikasi"},
        )
        self.assertIsNotNone(msg.id)
        saved = ChatMessage.objects.get(id=msg.id)
        self.assertEqual(saved.message, "Saya ingin magang di PT Telekomunikasi.")
        self.assertEqual(saved.sender, "user")

    def test_chat_message_api_view_post_ready_to_draft_contract(self):
        """
        Memastikan endpoint POST mengembalikan is_ready_to_draft: True, 
        intent, kode_surat, dan status ready_to_draft ketika seluruh slot wajib terpenuhi.
        """
        # Set session data di Redis / Manager dengan slot lengkap
        AutoSuratSessionManager.save_session(
            thread_id=str(self.thread.id),
            state="COLLECTING_SLOTS",
            intent="SR-MAG",
            slots={
                "instansi_tujuan": "PT Pertamina",
                "posisi_dilamar": "Full-Stack Developer",
                "chosen_destination": "email",
                "target_destination_address": "julian@pertamina.test",
            },
            missing_slots=[],
        )

        view = ChatSessionMessageAPIView.as_view()
        request = self.factory.post(
            f"/api/surat/chat/{self.thread.id}/",
            {"message": "lanjut"},
            format="json",
        )
        force_authenticate(request, user=self.user)

        with patch.object(AutoSuratSessionManager, "handle_incoming_message", return_value="Data lengkap."):
            response = view(request, thread_id=str(self.thread.id))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get("status"), "ready_to_draft")
        self.assertEqual(response.data.get("state"), "READY_TO_DRAFT")
        self.assertTrue(response.data.get("is_ready_to_draft"))
        self.assertEqual(response.data.get("intent"), "SR-MAG")
        self.assertEqual(response.data.get("kode_surat"), "SR-MAG")
        self.assertEqual(response.data.get("collected_slots", {}).get("instansi_tujuan"), "PT Pertamina")

    def test_chat_session_api_view_get_endpoint(self):
        """Memastikan endpoint GET /api/surat/chat/<thread_id>/ mengembalikan riwayat pesan dan snapshot sesi."""
        ChatMessage.objects.create(
            thread=self.thread,
            sender="user",
            message="Permohonan magang di PT Pertamina.",
        )
        ChatMessage.objects.create(
            thread=self.thread,
            sender="assistant",
            message="Siap, data posisi sudah dicatat.",
        )

        AutoSuratSessionManager.save_session(
            thread_id=str(self.thread.id),
            state="COLLECTING_SLOTS",
            intent="SR-MAG",
            slots={"instansi_tujuan": "PT Pertamina"},
            missing_slots=["posisi_dilamar"],
        )

        view = ChatSessionMessageAPIView.as_view()
        request = self.factory.get(f"/api/surat/chat/{self.thread.id}/")
        force_authenticate(request, user=self.user)

        response = view(request, thread_id=str(self.thread.id))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get("thread_id"), str(self.thread.id))
        self.assertEqual(response.data.get("intent"), "SR-MAG")
        self.assertFalse(response.data.get("is_ready_to_draft"))
        messages = response.data.get("messages", [])
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["sender"], "user")
        self.assertEqual(messages[1]["sender"], "assistant")


class IntentDetectionPipelineTestCase(TestCase):
    """
    Test suite untuk memvalidasi akurasi deteksi niat (Intent Detection):
    1. Memastikan input survey/observasi terklasifikasi sebagai SI-SUR (bukan SI-MAG)
    2. Memastikan surat izin magang terklasifikasi sebagai SI-MAG
    3. Memastikan surat rekomendasi magang terklasifikasi sebagai SR-MAG
    4. Memastikan surat keterangan aktif kuliah terklasifikasi sebagai SK-KUL
    5. Memastikan surat pengantar skck terklasifikasi sebagai SP-SKC
    """

    def setUp(self):
        SuratType.objects.get_or_create(kode_surat="SI-SUR", defaults={"nama_surat": "surat izin survey dan observasi"})
        SuratType.objects.get_or_create(kode_surat="SI-MAG", defaults={"nama_surat": "surat izin magang"})
        SuratType.objects.get_or_create(kode_surat="SR-MAG", defaults={"nama_surat": "surat rekomendasi magang"})
        SuratType.objects.get_or_create(kode_surat="SK-KUL", defaults={"nama_surat": "surat keterangan aktif kuliah"})
        SuratType.objects.get_or_create(kode_surat="SP-SKC", defaults={"nama_surat": "surat pengantar skck"})
        SuratType.objects.get_or_create(kode_surat="SP-TRA", defaults={"nama_surat": "surat pengantar transkip nilai"})
        SuratType.objects.get_or_create(kode_surat="SP-TAS", defaults={"nama_surat": "surat pengantar riset tugas akhir"})

    def test_detect_survey_observasi_resolves_to_si_sur(self):
        """Memastikan 'buatkan saya izin survey dan observasi' terdeteksi sebagai SI-SUR."""
        from surat.services.detect_intent import detect_intent_dynamically
        result = detect_intent_dynamically("buatkan saya izin survey dan observasi")
        self.assertEqual(result, "SI-SUR")

    def test_detect_izin_magang_resolves_to_si_mag(self):
        """Memastikan 'saya mau buat surat izin magang' terdeteksi sebagai SI-MAG."""
        from surat.services.detect_intent import detect_intent_dynamically
        result = detect_intent_dynamically("saya mau buat surat izin magang")
        self.assertEqual(result, "SI-MAG")

    def test_detect_rekomendasi_magang_resolves_to_sr_mag(self):
        """Memastikan 'rekomendasi magang' terdeteksi sebagai SR-MAG."""
        from surat.services.detect_intent import detect_intent_dynamically
        result = detect_intent_dynamically("rekomendasi magang pertamina")
        self.assertEqual(result, "SR-MAG")

    def test_detect_aktif_kuliah_resolves_to_sk_kul(self):
        """Memastikan 'surat keterangan aktif kuliah' terdeteksi sebagai SK-KUL."""
        from surat.services.detect_intent import detect_intent_dynamically
        result = detect_intent_dynamically("surat keterangan aktif kuliah untuk beasiswa")
        self.assertEqual(result, "SK-KUL")

    def test_detect_skck_resolves_to_sp_skc(self):
        """Memastikan 'pengantar skck' terdeteksi sebagai SP-SKC."""
        from surat.services.detect_intent import detect_intent_dynamically
        result = detect_intent_dynamically("pengantar skck kepolisian")
        self.assertEqual(result, "SP-SKC")


class ConversationFlowStructuredStatesTestCase(TestCase):
    """
    Test suite untuk memvalidasi alur percakapan terstruktur 4-State:
    State 1: Inisiasi Percakapan (Greeting resmi tanpa emoji)
    State 2: Penanganan Parameter Tidak Lengkap (Hanya meminta atribut kurang, DILARANG menampilkan parameter yang sudah ada)
    State 3: Konfirmasi data lengkap & Flag action_required == 'delivery_method'
    State 4: Eksekusi pilihan metode pengiriman oleh pengguna
    """

    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User.objects.create(
            id="u-std-flow-test",
            nama="Julian Sanchez",
            nip_nim="INF24001",
            role="STUDENT",
            password="password123",
        )
        self.user.is_authenticated = True

        self.surat_type = SuratType.objects.create(
            kode_surat="SI-SUR",
            nama_surat="surat izin survey dan observasi",
            required_payload_fields=[
                {"field": "instansi_tujuan", "label": "Instansi Tujuan"},
                {"field": "lokasi_kegiatan", "label": "Lokasi Kegiatan"},
                {"field": "tanggal_mulai", "label": "Tanggal Mulai"},
            ],
        )

        self.thread = ChatThread.objects.create(
            user=self.user,
            title="Sesi Permohonan Surat Izin Survey",
            document_type="SI-SUR",
            status=ChatThread.ThreadStatus.ACTIVE,
        )

    def test_state_1_greeting_when_no_intent(self):
        """Memastikan pesan pembuka baku digunakan saat obrolan tidak memuat intensi surat."""
        from surat.services.chat_workflow import handle_incoming_chat_with_redis
        session_data = {"slots": {}}
        reply = handle_incoming_chat_with_redis(str(self.thread.id), "halo selamat pagi", session_data)
        self.assertIn("Halo, saya adalah Asisten AI yang akan membantu Anda menyusun dokumen dan surat resmi.", reply)
        self.assertIn("Silakan deskripsikan jenis surat yang ingin Anda buat beserta detail keperluannya.", reply)

    def test_state_2_missing_entities_format_prohibits_existing_entities(self):
        """
        Memastikan State 2 hanya meminta parameter yang kurang,
        dan DILARANG menampilkan parameter yang sudah terisi.
        """
        from surat.services.chat_workflow import handle_incoming_chat_with_redis
        session_data = {
            "intent": "SI-SUR",
            "slots": {},
        }

        reply = handle_incoming_chat_with_redis(
            str(self.thread.id),
            "Instansi tujuan adalah Laboratorium Geologi",
            session_data,
        )
        
        # Harus memuat format baku State 2
        self.assertIn("Untuk melanjutkan pembuatan surat surat izin survey dan observasi, Anda harus melampirkan informasi berikut:", reply)
        self.assertIn("Lokasi Kegiatan", reply)
        self.assertIn("Tanggal Mulai", reply)
        
        # DILARANG menampilkan parameter yang sudah ada
        self.assertNotIn("Laboratorium Geologi", reply)
        self.assertNotIn("Instansi Tujuan", reply)

    def test_date_without_year_uses_current_year(self):
        """
        Kasus 1: Memastikan ketika user menginput tanggal tanpa tahun (misal '10 November'),
        sistem tidak mengarang tahun 2024 melainkan menggunakan tahun berjalan saat ini.
        """
        from surat.services.chat_workflow import (
            handle_incoming_chat_with_redis,
            get_current_year,
        )
        session_data = {
            "intent": "SI-SUR",
            "slots": {
                "instansi_tujuan": "Laboratorium Geologi",
                "lokasi_kegiatan": "Bandung",
            },
        }

        reply = handle_incoming_chat_with_redis(
            str(self.thread.id),
            "10 November",
            session_data,
        )
        expected_date = f"{get_current_year():04d}-11-10"
        self.assertEqual(session_data["slots"].get("tanggal_mulai"), expected_date)
        self.assertIn(expected_date, reply)
        self.assertNotIn("2024-11-10", reply)

    def test_invalid_slot_type_date_for_instansi_returns_correction_message(self):
        """
        Kasus 2: Memastikan ketika user menginput tanggal saat diminta parameter non-tanggal
        (seperti Instansi Tujuan), slot ditolak dan sistem mengembalikan pesan koreksi input salah.
        """
        from surat.services.chat_workflow import handle_incoming_chat_with_redis
        session_data = {
            "intent": "SI-SUR",
            "slots": {
                "tanggal_mulai": "2026-11-10",
            },
        }

        reply = handle_incoming_chat_with_redis(
            str(self.thread.id),
            "15 Desember",
            session_data,
        )
        self.assertNotIn("instansi_tujuan", session_data["slots"])
        self.assertNotIn("lokasi_kegiatan", session_data["slots"])
        # Pastikan tanggal_mulai yang sudah terisi sebelumnya tidak tertimpa
        self.assertEqual(session_data["slots"].get("tanggal_mulai"), "2026-11-10")
        self.assertIn("Input yang Anda masukkan tidak sesuai atau belum tepat.", reply)
        self.assertIn("Instansi Tujuan", reply)
        self.assertIn("Lokasi Kegiatan", reply)

    def test_state_3_complete_summary_and_action_required_flag(self):
        """
        Memastikan State 3 merangkum seluruh atribut dan mengembalikan
        flag action_required: 'delivery_method' pada API view.
        """
        # Set seluruh 3 slot terisi, namun chosen_destination belum terisi
        AutoSuratSessionManager.save_session(
            thread_id=str(self.thread.id),
            state="COLLECTING_SLOTS",
            intent="SI-SUR",
            slots={
                "instansi_tujuan": "PT Pertamina",
                "lokasi_kegiatan": "Jakarta Pusat",
                "tanggal_mulai": "2026-12-01",
            },
            missing_slots=[],
        )

        view = ChatSessionMessageAPIView.as_view()
        request = self.factory.post(
            f"/api/surat/chat/{self.thread.id}/",
            {"message": "2026-12-01"},
            format="json",
        )
        force_authenticate(request, user=self.user)

        response = view(request, thread_id=str(self.thread.id))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get("action_required"), "delivery_method")
        self.assertFalse(response.data.get("is_ready_to_draft"))
        
        reply = response.data.get("reply", "")
        self.assertIn("Seluruh data yang dibutuhkan telah lengkap. Berikut adalah rincian informasi surat Anda:", reply)
        self.assertIn("Instansi Tujuan: PT Pertamina", reply)
        self.assertIn("Lokasi Kegiatan: Jakarta Pusat", reply)
        self.assertIn("Tanggal Mulai: 2026-12-01", reply)
        self.assertIn("Surat Anda akan dikirim melalui apa?", reply)

    def test_state_4_execution_of_delivery_choice(self):
        """
        Memastikan ketika user memilih Email, sistem mencatat pilihan kanal pengiriman.
        """
        AutoSuratSessionManager.save_session(
            thread_id=str(self.thread.id),
            state="COLLECTING_SLOTS",
            intent="SI-SUR",
            slots={
                "instansi_tujuan": "PT Pertamina",
                "lokasi_kegiatan": "Jakarta Pusat",
                "tanggal_mulai": "2026-12-01",
            },
            missing_slots=[],
        )

        view = ChatSessionMessageAPIView.as_view()
        request = self.factory.post(
            f"/api/surat/chat/{self.thread.id}/",
            {"message": "Email: julian@pertamina.test"},
            format="json",
        )
        force_authenticate(request, user=self.user)

        response = view(request, thread_id=str(self.thread.id))
        self.assertEqual(response.status_code, 200)
        
        collected = response.data.get("collected_slots", {})
        self.assertEqual(collected.get("chosen_destination"), "email")
        self.assertEqual(collected.get("target_destination_address"), "julian@pertamina.test")
        self.assertTrue(response.data.get("is_ready_to_draft"))
        self.assertIsNone(response.data.get("action_required"))


class DefectFixesVerificationTestCase(TestCase):
    """Memverifikasi seluruh perbaikan bug pra-V2 pada chat_workflow, models, views, views_extra, agents, dan accounts."""

    def setUp(self):
        from rest_framework.test import APIClient
        self.client = APIClient()

        self.user_dekan = User.objects.create(
            id="u-dekan-fix",
            nama="Prof. Dekan Teknik",
            nip_nim="197001011999011001",
            role="LECTURER",
            password="pass",
        )
        self.user_kaprodi = User.objects.create(
            id="u-kaprodi-fix",
            nama="Dr. Kaprodi Informatika",
            nip_nim="198202022006011002",
            role="LECTURER",
            password="pass",
        )
        self.user_owner = User.objects.create(
            id="u-mhs-owner",
            nama="Mahasiswa Pemilik",
            nip_nim="210002001",
            role="STUDENT",
            password="pass",
        )
        self.user_other = User.objects.create(
            id="u-mhs-other",
            nama="Mahasiswa Lain",
            nip_nim="210002002",
            role="STUDENT",
            password="pass",
        )

        self.fakultas = Faculty.objects.create(id="FT-FIX", nama_fakultas="Fakultas Teknik")
        self.prodi = Department.objects.create(id="INF-FIX", fakultas=self.fakultas, nama_prodi="Informatika")

        self.lec_dekan = Lecturer.objects.create(
            id="l-dekan-fix",
            user=self.user_dekan,
            fakultas=self.fakultas,
            prodi=self.prodi,
            jabatan_struktural=["Dekan Fakultas Teknik"],
        )
        self.lec_kaprodi = Lecturer.objects.create(
            id="l-kaprodi-fix",
            user=self.user_kaprodi,
            fakultas=self.fakultas,
            prodi=self.prodi,
            jabatan_struktural=["Ketua Program Studi Informatika"],
        )
        self.fakultas.dekan = self.lec_dekan
        self.fakultas.save()
        self.prodi.kaprodi = self.lec_kaprodi
        self.prodi.save()

        self.student_owner = Student.objects.create(
            nim="210002001",
            user=self.user_owner,
            fakultas=self.fakultas,
            prodi=self.prodi,
            semester_aktif=7,
            tahun_akademik="2026/2027",
            tahun_masuk=2021,
        )
        self.student_other = Student.objects.create(
            nim="210002002",
            user=self.user_other,
            fakultas=self.fakultas,
            prodi=self.prodi,
            semester_aktif=5,
            tahun_akademik="2026/2027",
            tahun_masuk=2022,
        )

        self.type_custom = SuratType.objects.create(
            kode_surat="CUSTOM-SURAT",
            nama_surat="Surat Custom Pribadi",
            kategori="Custom",
            is_auto_approval=True,
            required_payload_fields=[{"field": "isi_permintaan", "label": "Isi Permintaan", "type": "string"}],
        )
        self.type_simag = SuratType.objects.create(
            kode_surat="SI-MAG",
            nama_surat="Surat Permohonan Izin Magang",
            kategori="Surat Izin",
            is_auto_approval=False,
            required_payload_fields=[
                {"field": "instansi_tujuan", "label": "Instansi", "type": "string"},
                {"field": "posisi_magang", "label": "Posisi Magang", "type": "string"},
                {"field": "tanggal_mulai", "label": "Tanggal Mulai", "type": "date"},
                {"field": "tanggal_selesai", "label": "Tanggal Selesai", "type": "date"},
            ],
        )
        self.type_skmk = SuratType.objects.create(
            kode_surat="SK-MK",
            nama_surat="Surat Keterangan Masih Kuliah",
            kategori="Surat Keterangan",
            is_auto_approval=False,
            required_payload_fields=[{"field": "keperluan_surat", "label": "Keperluan", "type": "string"}],
        )

    def test_chat_workflow_restored_regexes_and_catalog_slot_aliases(self):
        from surat.services.chat_workflow import (
            extract_composite_slots_deterministically,
            is_out_of_context_message,
            sanitize_extracted_slot,
        )

        slots_magang = extract_composite_slots_deterministically(
            "di PT Telkom Indonesia sebagai Backend Engineer dari tanggal 1 Mei 2026 sampai 30 Juli 2026",
            [
                {"field": "instansi_tujuan"},
                {"field": "posisi_magang"},
                {"field": "tanggal_mulai"},
                {"field": "tanggal_selesai"},
            ],
            {},
        )
        self.assertEqual(slots_magang.get("instansi_tujuan"), "PT Telkom Indonesia")
        self.assertEqual(slots_magang.get("posisi_magang"), "Backend Engineer")
        self.assertEqual(slots_magang.get("tanggal_mulai"), "2026-05-01")
        self.assertEqual(slots_magang.get("tanggal_selesai"), "2026-07-30")

        slots_skmk = extract_composite_slots_deterministically(
            "keperluan pengajuan beasiswa unggulan",
            [{"field": "keperluan_surat"}],
            {},
        )
        self.assertEqual(slots_skmk.get("keperluan_surat"), "Pengajuan Beasiswa Unggulan")
        self.assertTrue(is_out_of_context_message("kopi arabika enak?"))
        self.assertFalse(is_out_of_context_message("kopi arabika enak"))
        self.assertEqual(sanitize_extracted_slot("keperluan_surat", "untuk mengurus beasiswa"), "mengurus beasiswa")

    @patch("surat.services.pdf_generator_safe.generate_and_save_official_pdf", return_value="/tmp/custom_dummy.pdf")
    def test_custom_letter_status_sent_and_printed_not_overwritten(self, _mock_pdf):
        custom_req = SuratRequest.objects.create(
            student=self.student_owner,
            kode_surat=self.type_custom,
            final_approved_content="Isi surat izin kegiatan resmi organisasi.",
            ai_original_draft="Isi surat izin kegiatan resmi organisasi.",
            payload_data={"judul_surat": "SURAT IZIN KEGIATAN"},
        )
        self.assertEqual(custom_req.status, SuratStatus.APPROVED)

        custom_req.status = SuratStatus.PRINTED
        custom_req.save(update_fields=["status"])
        custom_req.refresh_from_db()
        self.assertEqual(custom_req.status, SuratStatus.PRINTED)

        custom_req.status = SuratStatus.SENT
        custom_req.save()
        custom_req.refresh_from_db()
        self.assertEqual(custom_req.status, SuratStatus.SENT)

    def test_chat_session_message_missing_thread_and_empty_body(self):
        self.client.force_authenticate(user=self.user_owner)
        res_missing = self.client.post("/api/surat/chat/00000000-0000-0000-0000-000000000000/", {}, format="json")
        self.assertEqual(res_missing.status_code, 404)

        thread = ChatThread.objects.create(user=self.user_owner, title="Sesi")
        res_empty = self.client.post(f"/api/surat/chat/{thread.id}/", {}, format="json")
        self.assertEqual(res_empty.status_code, 400)

    def test_drafting_worker_uses_min_score_8_via_evaluate_draft_readiness(self):
        from surat.views import _execute_drafting_agent_worker

        surat_req = SuratRequest.objects.create(
            student=self.student_owner,
            kode_surat=self.type_skmk,
            payload_data={"keperluan_surat": "Beasiswa"},
            status=SuratStatus.SUBMITTED,
        )
        mock_output = MagicMock()
        mock_output.to_payload_dict.return_value = {"keperluan_surat": "Beasiswa"}
        mock_output.ai_original_draft = "Draf surat keterangan."
        mock_output.evaluation.self_critique_score = 7
        mock_output.evaluation.revision_notes = ["Perlu perbaikan redaksi."]
        mock_output.evaluation.has_missing_info = False

        mock_agent = MagicMock()
        mock_agent.draft_letter.return_value = mock_output
        mock_agent.get_required_fields_for_kode.return_value = [
            {"field": "keperluan_surat", "label": "Keperluan Surat", "type": "string"}
        ]

        _execute_drafting_agent_worker(
            surat_request_id=surat_req.id,
            user_prompt_context="Keperluan beasiswa",
            kode_surat="SK-MK",
            agent=mock_agent,
        )
        surat_req.refresh_from_db()
        self.assertEqual(surat_req.status, SuratStatus.REVISION_REQUIRED)

    @patch("surat.views_extra._ensure_pdf_on_disk")
    @patch("surat.services.pdf_generator_safe.generate_and_save_official_pdf", return_value="/tmp/custom_dummy.pdf")
    def test_views_extra_auth_ownership_and_chat_feedback(self, _mock_pdf, mock_ensure_pdf):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_pdf:
            tmp_pdf.write(b"%PDF-1.4\n%test\n")
            tmp_pdf_path = tmp_pdf.name
        try:
            mock_ensure_pdf.return_value = tmp_pdf_path
            thread = ChatThread.objects.create(user=self.user_owner, title="Custom")
            custom_req = SuratRequest.objects.create(
                student=self.student_owner,
                kode_surat=self.type_custom,
                chat_thread=thread,
                final_approved_content="Isi surat custom pemilik.",
                ai_original_draft="Isi surat custom pemilik.",
                payload_data={"judul_surat": "SURAT PRIBADI"},
            )
            official_req = SuratRequest.objects.create(
                student=self.student_owner,
                kode_surat=self.type_simag,
                final_approved_content="Isi surat resmi magang.",
                payload_data={"instansi_tujuan": "PT ABC", "posisi_magang": "QA", "tanggal_mulai": "2026-05-01", "tanggal_selesai": "2026-06-01"},
                status=SuratStatus.APPROVED,
            )

            # 1. Anonymous blocked on preview/download/print/email/signature
            self.client.force_authenticate(user=None)
            self.assertEqual(self.client.get(f"/api/surat/requests/{custom_req.id}/preview-pdf/").status_code, 401)
            self.assertEqual(self.client.get(f"/api/surat/requests/{custom_req.id}/download-pdf/").status_code, 401)
            self.assertEqual(self.client.post(f"/api/surat/requests/{custom_req.id}/mark-printed/").status_code, 401)
            self.assertEqual(
                self.client.post(f"/api/surat/requests/{custom_req.id}/deliver-email/", {"recipient_email": "a@b.c"}).status_code,
                401,
            )
            self.assertEqual(self.client.post(f"/api/surat/requests/{custom_req.id}/upload-signature/").status_code, 401)

            # 2. Other student blocked (IDOR prevention)
            self.client.force_authenticate(user=self.user_other)
            self.assertEqual(self.client.get(f"/api/surat/requests/{official_req.id}/preview-pdf/").status_code, 403)
            self.assertEqual(self.client.post(f"/api/surat/requests/{custom_req.id}/mark-printed/").status_code, 403)

            # 3. Lecturer cannot preview CUSTOM letter, can preview official campus letter
            self.client.force_authenticate(user=self.user_kaprodi)
            self.assertEqual(self.client.get(f"/api/surat/requests/{custom_req.id}/preview-pdf/").status_code, 403)
            self.assertEqual(self.client.get(f"/api/surat/requests/{official_req.id}/preview-pdf/").status_code, 200)

            # 4. Owner can preview & mark-printed, persisting PRINTED + writing ChatMessage feedback
            self.client.force_authenticate(user=self.user_owner)
            self.assertEqual(self.client.get(f"/api/surat/requests/{custom_req.id}/preview-pdf/").status_code, 200)
            res_print = self.client.post(f"/api/surat/requests/{custom_req.id}/mark-printed/")
            self.assertEqual(res_print.status_code, 200)
            custom_req.refresh_from_db()
            self.assertEqual(custom_req.status, SuratStatus.PRINTED)
            self.assertTrue(ChatMessage.objects.filter(thread=thread, message__icontains="telah dicetak").exists())
        finally:
            import os
            if os.path.exists(tmp_pdf_path):
                os.remove(tmp_pdf_path)

    def test_resolve_signer_and_execution_tools_follow_dekan_kaprodi_catalog(self):
        from surat.views_extra import _resolve_signer

        req_simag = SuratRequest.objects.create(
            student=self.student_owner,
            kode_surat=self.type_simag,
            payload_data={},
            status=SuratStatus.APPROVED,
        )
        req_skmk = SuratRequest.objects.create(
            student=self.student_owner,
            kode_surat=self.type_skmk,
            payload_data={},
            status=SuratStatus.APPROVED,
        )

        self.assertEqual(_resolve_signer(req_simag)[1], self.user_kaprodi.nip_nim)
        self.assertEqual(_resolve_signer(req_skmk)[1], self.user_dekan.nip_nim)

        tools = SuratExecutionTools()
        ctx_simag = tools.build_pdf_template_context(
            req_simag,
            nomor_surat="001/SI-MAG/FT/2026",
            qr_code_url="https://example.test/verify/1",
        )
        ctx_skmk = tools.build_pdf_template_context(
            req_skmk,
            nomor_surat="002/SK-MK/FT/2026",
            qr_code_url="https://example.test/verify/2",
        )
        self.assertEqual(ctx_simag["signer_nip"], self.user_kaprodi.nip_nim)
        self.assertEqual(ctx_skmk["signer_nip"], self.user_dekan.nip_nim)

    def test_account_token_refresh_endpoint_returns_new_access_token(self):
        from rest_framework_simplejwt.tokens import RefreshToken

        refresh = RefreshToken()
        refresh["user_id"] = self.user_owner.id
        refresh["role"] = self.user_owner.role
        refresh["nip_nim"] = self.user_owner.nip_nim

        self.client.force_authenticate(user=None)
        res = self.client.post("/api/accounts/token/refresh/", {"refresh": str(refresh)}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertIn("access", res.data)

        res_bad = self.client.post("/api/accounts/token/refresh/", {"refresh": "invalid.token.value"}, format="json")
        self.assertEqual(res_bad.status_code, 401)


class V2DirectAutoIssuanceTestCase(TestCase):
    """Memverifikasi V2 Bagian A: penghapusan gate approval dosen & penerbitan otomatis langsung."""

    def setUp(self):
        from rest_framework.test import APIClient
        self.client = APIClient()

        self.user_dekan = User.objects.create(
            id="u-v2-dekan",
            nama="Prof. V2 Dekan",
            nip_nim="197101011999011001",
            role="LECTURER",
            password="pass",
        )
        self.user_kaprodi = User.objects.create(
            id="u-v2-kaprodi",
            nama="Dr. V2 Kaprodi INF",
            nip_nim="198303032007011003",
            role="LECTURER",
            password="pass",
        )
        self.user_other_kaprodi = User.objects.create(
            id="u-v2-other-kaprodi",
            nama="Dr. V2 Kaprodi SI",
            nip_nim="198404042008011004",
            role="LECTURER",
            password="pass",
        )
        self.user_mhs = User.objects.create(
            id="u-v2-mhs",
            nama="Bintang Mahasiswa",
            nip_nim="210003001",
            role="STUDENT",
            password="pass",
        )
        self.user_other_mhs = User.objects.create(
            id="u-v2-other-mhs",
            nama="Citra Mahasiswa SI",
            nip_nim="210003002",
            role="STUDENT",
            password="pass",
        )

        self.fak_ft = Faculty.objects.create(id="FT-V2", nama_fakultas="Fakultas Teknik")
        self.fak_feb = Faculty.objects.create(id="FEB-V2", nama_fakultas="Fakultas Ekonomi")
        self.prodi_inf = Department.objects.create(id="INF-V2", fakultas=self.fak_ft, nama_prodi="Informatika")
        self.prodi_si = Department.objects.create(id="SI-V2", fakultas=self.fak_feb, nama_prodi="Akuntansi")

        self.lec_dekan = Lecturer.objects.create(
            id="l-v2-dekan",
            user=self.user_dekan,
            fakultas=self.fak_ft,
            prodi=self.prodi_inf,
            jabatan_struktural=["Dekan Fakultas Teknik"],
        )
        self.lec_kaprodi = Lecturer.objects.create(
            id="l-v2-kaprodi",
            user=self.user_kaprodi,
            fakultas=self.fak_ft,
            prodi=self.prodi_inf,
            jabatan_struktural=["Ketua Program Studi Informatika"],
        )
        self.lec_other = Lecturer.objects.create(
            id="l-v2-other-kaprodi",
            user=self.user_other_kaprodi,
            fakultas=self.fak_feb,
            prodi=self.prodi_si,
            jabatan_struktural=["Ketua Program Studi Akuntansi"],
        )
        self.fak_ft.dekan = self.lec_dekan
        self.fak_ft.save()
        self.prodi_inf.kaprodi = self.lec_kaprodi
        self.prodi_inf.save()
        self.prodi_si.kaprodi = self.lec_other
        self.prodi_si.save()

        self.student_inf = Student.objects.create(
            nim="210003001",
            user=self.user_mhs,
            fakultas=self.fak_ft,
            prodi=self.prodi_inf,
            semester_aktif=7,
            tahun_akademik="2026/2027",
            tahun_masuk=2022,
            total_sks_lulus=110,
            ipk_kumulatif=3.75,
        )
        self.student_si = Student.objects.create(
            nim="210003002",
            user=self.user_other_mhs,
            fakultas=self.fak_feb,
            prodi=self.prodi_si,
            semester_aktif=5,
            tahun_akademik="2026/2027",
            tahun_masuk=2023,
        )

        from surat.services.campus_catalog import ensure_campus_surat_types
        ensure_campus_surat_types()
        self.type_simag = SuratType.objects.get(kode_surat="SI-MAG")
        self.type_skmk = SuratType.objects.get(kode_surat="SK-MK")
        self.type_custom = SuratType.objects.get(kode_surat="CUSTOM-UMUM")

    def test_catalog_and_settings_enable_auto_issuance_by_default(self):
        from django.conf import settings
        from surat.services.campus_catalog import CAMPUS_SURAT_CATALOG

        self.assertFalse(getattr(settings, "REQUIRE_MANUAL_APPROVAL", True))
        self.assertTrue(all(item.get("is_auto_approval") is True for item in CAMPUS_SURAT_CATALOG))
        self.assertTrue(self.type_simag.is_auto_approval)
        self.assertTrue(self.type_skmk.is_auto_approval)

    @patch("surat.services.pdf_generator_safe.generate_and_save_official_pdf", return_value="/tmp/v2_auto_magang.pdf")
    def test_request_and_draft_worker_auto_issues_without_lecturer_approval(self, _mock_pdf):
        from surat.models import Notification, TteSignature
        from surat.views import _execute_drafting_agent_worker

        thread = ChatThread.objects.create(user=self.user_mhs, title="Izin Magang V2")
        payload = {
            "instansi_tujuan": "PT Telkom Indonesia",
            "posisi_magang": "Backend Engineer",
            "tanggal_mulai": "2026-06-01",
            "tanggal_selesai": "2026-08-31",
        }

        mock_output = MagicMock()
        mock_output.to_payload_dict.return_value = payload
        mock_output.ai_original_draft = "Dengan hormat, kami memohon izin magang di PT Telkom Indonesia."
        mock_output.evaluation.self_critique_score = 9
        mock_output.evaluation.revision_notes = []
        mock_output.evaluation.has_missing_info = False

        mock_agent = MagicMock()
        mock_agent.draft_letter.return_value = mock_output
        mock_agent.get_required_fields_for_kode.return_value = self.type_simag.required_payload_fields

        def _sync_thread(target, kwargs=None, daemon=None):
            m = MagicMock()
            m.start.side_effect = lambda: target(**(kwargs or {}))
            return m

        self.client.force_authenticate(user=self.user_mhs)
        with self.captureOnCommitCallbacks(execute=True), patch(
            "surat.views.threading.Thread", side_effect=_sync_thread
        ), patch("surat.views.SuratRequestCreateAPIView.get_drafting_agent", return_value=mock_agent):
            res = self.client.post(
                "/api/surat/request/",
                {
                    "kode_surat": "SI-MAG",
                    "user_prompt_context": "Izin magang ke PT Telkom Indonesia",
                    "payload_data": payload,
                    "thread_id": str(thread.id),
                },
                format="json",
            )

        self.assertEqual(res.status_code, 202)
        self.assertIn("diterbitkan otomatis", res.data["message"])
        req_id = res.data["request_id"]
        surat_req = SuratRequest.objects.get(pk=req_id)

        self.assertEqual(surat_req.status, SuratStatus.APPROVED)
        self.assertTrue(bool(surat_req.nomor_surat_resmi))
        self.assertTrue(bool(surat_req.qr_verification_code))
        self.assertTrue(bool(surat_req.file_pdf_url))
        self.assertEqual(SuratApproval.objects.filter(surat_request=surat_req).count(), 0)
        self.assertFalse(Notification.objects.filter(type="APPROVAL_REQUIRED").exists())

        tte = TteSignature.objects.get(surat_request=surat_req)
        self.assertEqual(tte.signer_id, self.lec_kaprodi.pk)
        self.assertTrue(Notification.objects.filter(user=self.user_mhs, type="APPROVED", surat_request=surat_req).exists())
        self.assertTrue(ChatMessage.objects.filter(thread=thread, message__icontains="Telah Terbit").exists())

    @patch("surat.services.pdf_generator_safe.generate_and_save_official_pdf", return_value="/tmp/v2_auto_redraft.pdf")
    def test_revision_required_then_redraft_auto_issues_without_approval(self, _mock_pdf):
        from surat.models import Notification

        thread = ChatThread.objects.create(user=self.user_mhs, title="SK-MK V2")
        bad_output = MagicMock()
        bad_output.to_payload_dict.return_value = {"keperluan_surat": ""}
        bad_output.ai_original_draft = "Draf belum lengkap."
        bad_output.evaluation.self_critique_score = 6
        bad_output.evaluation.revision_notes = ["Keperluan surat belum diisi."]
        bad_output.evaluation.has_missing_info = True

        good_output = MagicMock()
        good_output.to_payload_dict.return_value = {"keperluan_surat": "Pengajuan Beasiswa Bank Indonesia"}
        good_output.ai_original_draft = "Menerangkan bahwa mahasiswa aktif kuliah untuk Pengajuan Beasiswa Bank Indonesia."
        good_output.evaluation.self_critique_score = 9
        good_output.evaluation.revision_notes = []
        good_output.evaluation.has_missing_info = False

        mock_agent = MagicMock()
        mock_agent.draft_letter.return_value = bad_output
        mock_agent.draft_letter_with_reflection.return_value = good_output
        mock_agent.get_required_fields_for_kode.return_value = self.type_skmk.required_payload_fields

        def _sync_thread(target, kwargs=None, daemon=None):
            m = MagicMock()
            m.start.side_effect = lambda: target(**(kwargs or {}))
            return m

        self.client.force_authenticate(user=self.user_mhs)
        with self.captureOnCommitCallbacks(execute=True), patch(
            "surat.views.threading.Thread", side_effect=_sync_thread
        ), patch("surat.views.SuratRequestCreateAPIView.get_drafting_agent", return_value=mock_agent):
            res_create = self.client.post(
                "/api/surat/request/",
                {
                    "kode_surat": "SK-MK",
                    "user_prompt_context": "Butuh surat masih kuliah",
                    "payload_data": {},
                    "thread_id": str(thread.id),
                },
                format="json",
            )

        req_id = res_create.data["request_id"]
        surat_req = SuratRequest.objects.get(pk=req_id)
        self.assertEqual(surat_req.status, SuratStatus.REVISION_REQUIRED)
        self.assertEqual(SuratApproval.objects.filter(surat_request=surat_req).count(), 0)
        self.assertTrue(Notification.objects.filter(user=self.user_mhs, type="REVISION_REQUIRED", surat_request=surat_req).exists())

        with self.captureOnCommitCallbacks(execute=True), patch(
            "surat.views.threading.Thread", side_effect=_sync_thread
        ), patch("surat.views.SuratRequestRedraftAPIView.get_drafting_agent", return_value=mock_agent):
            res_redraft = self.client.post(
                f"/api/surat/requests/{req_id}/re-draft/",
                {
                    "additional_prompt_context": "Keperluan pengajuan Beasiswa Bank Indonesia",
                    "payload_data": {"keperluan_surat": "Pengajuan Beasiswa Bank Indonesia"},
                },
                format="json",
            )

        self.assertEqual(res_redraft.status_code, 202)
        self.assertIn("diterbitkan otomatis", res_redraft.data["message"])
        surat_req.refresh_from_db()
        self.assertEqual(surat_req.status, SuratStatus.APPROVED)
        self.assertTrue(bool(surat_req.nomor_surat_resmi))
        self.assertEqual(SuratApproval.objects.filter(surat_request=surat_req).count(), 0)

    def test_bridged_save_does_not_create_approval_queue_when_manual_disabled(self):
        req = SuratRequest.objects.create(
            student=self.student_inf,
            kode_surat=self.type_simag,
            status=SuratStatus.PENDING_APPROVAL,
            payload_data={},
        )
        self.assertEqual(SuratApproval.objects.filter(surat_request=req).count(), 0)

    def test_lecturer_approval_endpoint_disabled_and_list_is_scoped_readonly(self):
        req_inf = SuratRequest.objects.create(
            student=self.student_inf,
            kode_surat=self.type_simag,
            status=SuratStatus.APPROVED,
            nomor_surat_resmi="001/SI-MAG/FT/2026",
            payload_data={},
        )
        req_si = SuratRequest.objects.create(
            student=self.student_si,
            kode_surat=self.type_skmk,
            status=SuratStatus.APPROVED,
            nomor_surat_resmi="002/SK-MK/FEB/2026",
            payload_data={},
        )
        with patch("surat.services.pdf_generator_safe.generate_and_save_official_pdf", return_value="/tmp/c.pdf"):
            req_custom = SuratRequest.objects.create(
                student=self.student_inf,
                kode_surat=self.type_custom,
                final_approved_content="Surat pribadi mahasiswa.",
                payload_data={"judul_surat": "SURAT PRIBADI"},
            )

        # Approval endpoint returns 410 Gone
        self.client.force_authenticate(user=self.user_kaprodi)
        res_action = self.client.post(
            "/api/surat/approval/999/action/",
            {"action": "APPROVE"},
            format="json",
        )
        self.assertEqual(res_action.status_code, 410)

        # Kaprodi INF sees req_inf (same prodi, zero approvals needed), not req_si or CUSTOM
        res_list = self.client.get("/api/surat/requests/")
        self.assertEqual(res_list.status_code, 200)
        ids_kaprodi = [row["id"] for row in res_list.data]
        self.assertIn(req_inf.id, ids_kaprodi)
        self.assertNotIn(req_si.id, ids_kaprodi)
        self.assertNotIn(req_custom.id, ids_kaprodi)

        # Dekan FT sees FT letters and excludes FEB & CUSTOM
        self.client.force_authenticate(user=self.user_dekan)
        res_dekan = self.client.get("/api/surat/requests/")
        ids_dekan = [row["id"] for row in res_dekan.data]
        self.assertIn(req_inf.id, ids_dekan)
        self.assertNotIn(req_si.id, ids_dekan)
        self.assertNotIn(req_custom.id, ids_dekan)

        # Lecturer preview PDF blocked for out-of-scope faculty letter
        self.assertEqual(self.client.get(f"/api/surat/requests/{req_si.id}/preview-pdf/").status_code, 403)


class V2AiDraftCalibrationAndLecturerLetterTestCase(TestCase):
    """
    Memverifikasi:
    1. Menu Draft Surat AI (maks 5 draf terakhir per kode_surat, filter kategori, scoping prodi/fakultas, blokir CUSTOM & STUDENT).
    2. Kalibrasi draf AI melatih AgentFeedbackMemory (termasuk reference_draft) tanpa mengubah PDF/TTE historis mahasiswa,
       plus toggle aktif/nonaktif memori memengaruhi SuratDraftingAgent.
    3. Akun LECTURER dapat membuat surat resmi maupun surat custom pribadi dengan alur otomatis yang sama seperti mahasiswa.
    """

    def setUp(self):
        from rest_framework.test import APIClient
        self.client = APIClient()

        self.user_dekan = User.objects.create(
            id="u-cal-dekan",
            nama="Prof. Cal Dekan",
            nip_nim="197001011998011001",
            role="LECTURER",
            email="dekan.cal@example.ac.id",
            password="pass",
        )
        self.user_kaprodi = User.objects.create(
            id="u-cal-kaprodi",
            nama="Dr. Cal Kaprodi INF",
            nip_nim="198202022006011002",
            role="LECTURER",
            email="kaprodi.cal@example.ac.id",
            password="pass",
        )
        self.user_mhs_inf = User.objects.create(
            id="u-cal-mhs-inf",
            nama="Ayu Informatika",
            nip_nim="210004001",
            role="STUDENT",
            email="ayu.cal@example.ac.id",
            password="pass",
        )
        self.user_mhs_si = User.objects.create(
            id="u-cal-mhs-si",
            nama="Bagas Akuntansi",
            nip_nim="210004002",
            role="STUDENT",
            email="bagas.cal@example.ac.id",
            password="pass",
        )

        self.fak_ft = Faculty.objects.create(id="FT-CAL", nama_fakultas="Fakultas Teknik")
        self.fak_feb = Faculty.objects.create(id="FEB-CAL", nama_fakultas="Fakultas Ekonomi")
        self.prodi_inf = Department.objects.create(id="INF-CAL", fakultas=self.fak_ft, nama_prodi="Informatika")
        self.prodi_si = Department.objects.create(id="SI-CAL", fakultas=self.fak_feb, nama_prodi="Akuntansi")

        self.lec_dekan = Lecturer.objects.create(
            id="l-cal-dekan",
            user=self.user_dekan,
            fakultas=self.fak_ft,
            prodi=self.prodi_inf,
            jabatan_struktural=["Dekan Fakultas Teknik"],
        )
        self.lec_kaprodi = Lecturer.objects.create(
            id="l-cal-kaprodi",
            user=self.user_kaprodi,
            fakultas=self.fak_ft,
            prodi=self.prodi_inf,
            jabatan_struktural=["Ketua Program Studi Informatika"],
        )
        self.fak_ft.dekan = self.lec_dekan
        self.fak_ft.save()
        self.prodi_inf.kaprodi = self.lec_kaprodi
        self.prodi_inf.save()

        self.student_inf = Student.objects.create(
            nim="210004001",
            user=self.user_mhs_inf,
            fakultas=self.fak_ft,
            prodi=self.prodi_inf,
            semester_aktif=7,
            tahun_akademik="2026/2027",
            tahun_masuk=2022,
            total_sks_lulus=110,
            ipk_kumulatif=3.70,
        )
        self.student_si = Student.objects.create(
            nim="210004002",
            user=self.user_mhs_si,
            fakultas=self.fak_feb,
            prodi=self.prodi_si,
            semester_aktif=5,
            tahun_akademik="2026/2027",
            tahun_masuk=2023,
        )

        from surat.services.campus_catalog import ensure_campus_surat_types
        ensure_campus_surat_types()
        self.type_simag = SuratType.objects.get(kode_surat="SI-MAG")
        self.type_skmk = SuratType.objects.get(kode_surat="SK-MK")
        self.type_custom = SuratType.objects.get(kode_surat="CUSTOM-UMUM")

    def test_ai_drafts_returns_max_five_per_type_scoped_and_blocks_student(self):
        created_inf_ids = []
        for idx in range(7):
            req = SuratRequest.objects.create(
                student=self.student_inf,
                kode_surat=self.type_simag,
                status=SuratStatus.APPROVED,
                nomor_surat_resmi=f"0{idx+1}/SI-MAG/FT/2026",
                ai_original_draft=f"Draf AI SI-MAG ke-{idx+1}",
                final_approved_content=f"Draf AI SI-MAG ke-{idx+1}",
                self_critique_score=8,
                payload_data={"instansi_tujuan": f"Perusahaan {idx+1}"},
            )
            created_inf_ids.append(req.id)

        # Out-of-scope FEB letter and private CUSTOM letter
        SuratRequest.objects.create(
            student=self.student_si,
            kode_surat=self.type_skmk,
            status=SuratStatus.APPROVED,
            ai_original_draft="Draf FEB tidak boleh muncul untuk Kaprodi INF.",
            payload_data={},
        )
        with patch("surat.services.pdf_generator_safe.generate_and_save_official_pdf", return_value="/tmp/custom.pdf"):
            SuratRequest.objects.create(
                student=self.student_inf,
                kode_surat=self.type_custom,
                ai_original_draft="Draf Custom Pribadi.",
                final_approved_content="Draf Custom Pribadi.",
                payload_data={"judul_surat": "CUSTOM"},
            )

        # Student forbidden
        self.client.force_authenticate(user=self.user_mhs_inf)
        self.assertEqual(self.client.get("/api/surat/ai-drafts/").status_code, 403)

        # Kaprodi sees max 5 latest SI-MAG drafts, no FEB SK-MK, and no CUSTOM group
        self.client.force_authenticate(user=self.user_kaprodi)
        res = self.client.get("/api/surat/ai-drafts/")
        self.assertEqual(res.status_code, 200)
        self.assertGreaterEqual(len(res.data["categories"]), 1)

        groups_by_kode = {g["kode_surat"]: g for g in res.data["groups"]}
        self.assertIn("SI-MAG", groups_by_kode)
        self.assertNotIn("CUSTOM-UMUM", groups_by_kode)

        simag_drafts = groups_by_kode["SI-MAG"]["drafts"]
        self.assertEqual(len(simag_drafts), 5)
        self.assertEqual([d["id"] for d in simag_drafts], list(reversed(created_inf_ids[-5:])))
        self.assertEqual(len(groups_by_kode["SK-MK"]["drafts"]), 0)

        # Category filter narrows groups
        res_cat = self.client.get("/api/surat/ai-drafts/", {"kategori": "Surat Izin"})
        self.assertEqual(res_cat.status_code, 200)
        self.assertTrue(all(g["kategori"] == "Surat Izin" for g in res_cat.data["groups"]))

    def test_calibration_feedback_trains_memory_without_altering_historical_pdf_and_toggles(self):
        from surat.models import AgentFeedbackMemory, TteSignature
        from surat.agents.letter_agent import SuratDraftingAgent
        from surat.agents.memory_agent import AgenticMemoryAgent, MemoryDiffEvaluationSchema

        original_text = "Dengan hormat, kami mengajukan izin magang untuk mahasiswa di bawah ini."
        edited_text = (
            "Dengan hormat, Ketua Program Studi Informatika mengajukan permohonan resmi "
            "izin kerja praktik dan magang industri sesuai ketentuan akademik fakultas."
        )

        req = SuratRequest.objects.create(
            student=self.student_inf,
            kode_surat=self.type_simag,
            status=SuratStatus.APPROVED,
            nomor_surat_resmi="088/SI-MAG/FT/2026",
            file_pdf_url="/media/surat/archived_088.pdf",
            qr_verification_code="qr-cal-088",
            ai_original_draft=original_text,
            final_approved_content=original_text,
            self_critique_score=8,
            payload_data={"instansi_tujuan": "PT Astra"},
        )
        tte = TteSignature.objects.create(
            surat_request=req,
            signer=self.lec_kaprodi,
            token="qr-cal-088",
            hash_document="hash_immutable_088",
        )

        self.client.force_authenticate(user=self.user_kaprodi)

        # Identical edit does not create noisy memory rule
        res_same = self.client.post(
            f"/api/surat/ai-drafts/{req.id}/feedback/",
            {"edited_draft": original_text},
            format="json",
        )
        self.assertEqual(res_same.status_code, 200)
        self.assertFalse(res_same.data["learned"])
        self.assertEqual(res_same.data["status"], "no_significant_change")

        mock_eval = MemoryDiffEvaluationSchema(
            is_significant=True,
            diff_summary="Penambahan redaksi resmi Ketua Program Studi dan istilah magang industri.",
            extracted_rule="Gunakan frasa permohonan resmi Ketua Program Studi Informatika pada pembuka SI-MAG.",
            style_guidelines=["Gunakan diksi magang industri sesuai ketentuan akademik fakultas."],
        )
        with patch.object(AgenticMemoryAgent, "_invoke_diff_llm", return_value=mock_eval):
            res_cal = self.client.post(
                f"/api/surat/ai-drafts/{req.id}/feedback/",
                {"edited_draft": edited_text},
                format="json",
            )

        self.assertEqual(res_cal.status_code, 200)
        self.assertTrue(res_cal.data["learned"])
        self.assertEqual(res_cal.data["status"], "learned")
        mem_id = res_cal.data["memory"]["id"]
        self.assertEqual(res_cal.data["memory"]["reference_draft"], edited_text)

        # Issued student letter & TTE must remain untouched
        req.refresh_from_db()
        tte.refresh_from_db()
        self.assertEqual(req.final_approved_content, original_text)
        self.assertEqual(req.status, SuratStatus.APPROVED)
        self.assertEqual(req.file_pdf_url, "/media/surat/archived_088.pdf")
        self.assertEqual(req.nomor_surat_resmi, "088/SI-MAG/FT/2026")
        self.assertEqual(tte.hash_document, "hash_immutable_088")

        # Drafting agent picks up both the learned rule and the calibrated exemplar
        drafting_agent = SuratDraftingAgent.__new__(SuratDraftingAgent)
        meta = {
            "fakultas": self.fak_ft.nama_fakultas,
            "prodi": self.prodi_inf.nama_prodi,
        }
        rules = drafting_agent._load_active_style_rules("SI-MAG", student_metadata=meta)
        self.assertTrue(any("Ketua Program Studi Informatika" in r for r in rules))
        exemplar = SuratDraftingAgent._load_lecturer_exemplar("SI-MAG")
        self.assertIn("kerja praktik dan magang industri", exemplar)

        # List & toggle off rule
        res_mem_list = self.client.get("/api/surat/ai-feedback-memories/", {"kode_surat": "SI-MAG"})
        self.assertEqual(res_mem_list.status_code, 200)
        self.assertTrue(any(m["id"] == mem_id and m["is_active"] for m in res_mem_list.data))

        res_toggle = self.client.patch(
            f"/api/surat/ai-feedback-memories/{mem_id}/",
            {"is_active": False},
            format="json",
        )
        self.assertEqual(res_toggle.status_code, 200)
        self.assertFalse(res_toggle.data["is_active"])
        self.assertFalse(AgentFeedbackMemory.objects.get(pk=mem_id).is_active)

        rules_after = drafting_agent._load_active_style_rules("SI-MAG", student_metadata=meta)
        self.assertFalse(any("Ketua Program Studi Informatika" in r for r in rules_after))
        self.assertEqual(SuratDraftingAgent._load_lecturer_exemplar("SI-MAG"), "")

    @patch("surat.views_extra.send_surat_via_gmail_admin", return_value={"status": "SUCCESS", "message": "Sent"})
    @patch("surat.views_extra.generate_and_save_official_pdf", return_value="/tmp/lecturer_auto.pdf")
    @patch("surat.services.pdf_generator_safe.generate_and_save_official_pdf", return_value="/tmp/lecturer_auto.pdf")
    def test_lecturer_can_create_official_and_custom_letters_end_to_end(self, _mock_pdf, _mock_pdf_extra, _mock_email):
        # 1. Init chat as lecturer
        self.client.force_authenticate(user=self.user_kaprodi)
        res_init = self.client.post(
            "/api/surat/chat/init/",
            {"title": "Permohonan Surat Tugas Dosen"},
            format="json",
        )
        self.assertEqual(res_init.status_code, 201)
        thread_id = res_init.data["thread_id"]

        payload = {
            "instansi_tujuan": "BRIN Jakarta",
            "posisi_magang": "Peneliti Tamu",
            "tanggal_mulai": "2026-07-01",
            "tanggal_selesai": "2026-07-15",
        }
        mock_output = MagicMock()
        mock_output.to_payload_dict.return_value = payload
        mock_output.ai_original_draft = "Surat pengantar resmi dosen Kaprodi Informatika ke BRIN Jakarta."
        mock_output.evaluation.self_critique_score = 9
        mock_output.evaluation.revision_notes = []
        mock_output.evaluation.has_missing_info = False

        mock_agent = MagicMock()
        mock_agent.draft_letter.return_value = mock_output
        mock_agent.draft_letter_with_reflection.return_value = mock_output
        mock_agent.get_required_fields_for_kode.return_value = self.type_simag.required_payload_fields

        def _sync_thread(target, kwargs=None, daemon=None):
            m = MagicMock()
            m.start.side_effect = lambda: target(**(kwargs or {}))
            return m

        # 2. Create official letter as lecturer (student=None, requester_lecturer=self.lec_kaprodi)
        with self.captureOnCommitCallbacks(execute=True), patch(
            "surat.views.threading.Thread", side_effect=_sync_thread
        ), patch("surat.views.SuratRequestCreateAPIView.get_drafting_agent", return_value=mock_agent):
            res_req = self.client.post(
                "/api/surat/request/",
                {
                    "kode_surat": "SI-MAG",
                    "user_prompt_context": "Mohon surat kunjungan riset ke BRIN Jakarta",
                    "payload_data": payload,
                    "thread_id": thread_id,
                },
                format="json",
            )

        self.assertEqual(res_req.status_code, 202)
        req_id = res_req.data["request_id"]
        lecturer_req = SuratRequest.objects.get(pk=req_id)
        self.assertIsNone(lecturer_req.student)
        self.assertEqual(lecturer_req.requester_lecturer_id, self.lec_kaprodi.id)
        self.assertEqual(lecturer_req.status, SuratStatus.APPROVED)
        self.assertTrue(bool(lecturer_req.nomor_surat_resmi))
        self.assertEqual(SuratApproval.objects.filter(surat_request=lecturer_req).count(), 0)

        # Detail & lifecycle endpoints for author lecturer
        res_detail = self.client.get(f"/api/surat/requests/{req_id}/")
        self.assertEqual(res_detail.status_code, 200)
        self.assertEqual(res_detail.data["requester_role"], "LECTURER")
        self.assertEqual(res_detail.data["nama_mahasiswa"], self.user_kaprodi.nama)

        import tempfile
        import os
        fd, tmp_pdf_path = tempfile.mkstemp(suffix=".pdf")
        with os.fdopen(fd, "wb") as fp:
            fp.write(b"%PDF-1.4\n%mock\n")
        try:
            with patch("surat.views_extra._ensure_pdf_on_disk", return_value=tmp_pdf_path):
                res_preview = self.client.get(f"/api/surat/requests/{req_id}/preview-pdf/")
                self.assertEqual(res_preview.status_code, 200)
                self.assertEqual(res_preview["Content-Type"], "application/pdf")
        finally:
            if os.path.exists(tmp_pdf_path):
                os.remove(tmp_pdf_path)
        res_print = self.client.post(f"/api/surat/requests/{req_id}/mark-printed/", {}, format="json")
        self.assertEqual(res_print.status_code, 200)

        res_email = self.client.post(
            f"/api/surat/requests/{req_id}/deliver-email/",
            {"recipient_email": "kaprodi.cal@example.ac.id"},
            format="json",
        )
        self.assertEqual(res_email.status_code, 200)

        from surat.models import TteSignature
        tte_sig = TteSignature.objects.get(surat_request=lecturer_req)
        res_verify = self.client.get(f"/api/surat/verify/{tte_sig.token}/")
        self.assertEqual(res_verify.status_code, 200)
        self.assertEqual(res_verify.data["status"], "VALID")
        self.assertEqual(res_verify.data["mahasiswa"]["requester_role"], "LECTURER")

        with self.captureOnCommitCallbacks(execute=True), patch(
            "surat.views.threading.Thread", side_effect=_sync_thread
        ), patch("surat.views.SuratRequestRedraftAPIView.get_drafting_agent", return_value=mock_agent):
            res_redraft = self.client.post(
                f"/api/surat/requests/{req_id}/re-draft/",
                {"additional_prompt_context": "Tambahkan periode riset bulan Juli 2026."},
                format="json",
            )
        self.assertEqual(res_redraft.status_code, 202)

        # 3. Private CUSTOM letter created by lecturer remains hidden from other lecturers (Dekan), visible in ?mine=1
        with patch("surat.views.threading.Thread", side_effect=_sync_thread), patch(
            "surat.views.SuratRequestCreateAPIView.get_drafting_agent", return_value=mock_agent
        ):
            res_custom = self.client.post(
                "/api/surat/request/",
                {
                    "kode_surat": "CUSTOM-UMUM",
                    "user_prompt_context": "Surat pribadi catatan seminar pribadi dosen",
                    "payload_data": {"judul_surat": "SURAT PRIBADI DOSEN", "isi_surat": "Keperluan pribadi."},
                },
                format="json",
            )
        self.assertEqual(res_custom.status_code, 202)
        custom_id = res_custom.data["request_id"]

        res_mine = self.client.get("/api/surat/requests/", {"mine": 1})
        self.assertEqual(res_mine.status_code, 200)
        self.assertIn(custom_id, [row["id"] for row in res_mine.data])

        # Dekan cannot see Kaprodi's private CUSTOM letter in monitoring list, detail (404), or preview-pdf (403)
        self.client.force_authenticate(user=self.user_dekan)
        res_dekan_list = self.client.get("/api/surat/requests/")
        self.assertNotIn(custom_id, [row["id"] for row in res_dekan_list.data])
        self.assertEqual(self.client.get(f"/api/surat/requests/{custom_id}/").status_code, 404)
        self.assertEqual(self.client.get(f"/api/surat/requests/{custom_id}/preview-pdf/").status_code, 403)

