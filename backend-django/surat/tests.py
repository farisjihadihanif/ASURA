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
