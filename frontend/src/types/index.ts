export type UserRole = "STUDENT" | "LECTURER" | "STAFF" | "ADMIN";

export type SuratStatusCode =
  | "SUBMITTED"
  | "REVISION_REQUIRED"
  | "PENDING_APPROVAL"
  | "IN_REVIEW"
  | "APPROVED"
  | "REJECTED"
  | "SENT"
  | "PRINTED"
  | "FAILED";

export interface User {
  id: string;
  nama: string;
  nip_nim: string;
  role: UserRole;
  email?: string;
  profile?: {
    nim?: string;
    prodi?: string;
    fakultas?: string;
    user_id?: string;
  };
}

export interface AuthResponse {
  message: string;
  refresh: string;
  access: string;
  user: User;
}

export interface SuratType {
  kode_surat: string;
  nama_surat: string;
  kategori: string;
  is_auto_approval: boolean;
}

export interface SuratApproval {
  id: number;
  step_order: number;
  approver: string;
  approver_name: string | null;
  approver_nip: string | null;
  status: "WAITING" | "PENDING" | "APPROVED" | "REJECTED";
  catatan: string | null;
  created_at: string | null;
}

export interface SuratRequestListItem {
  id: number;
  nim_mahasiswa: string;
  nama_mahasiswa: string;
  requester_role?: "STUDENT" | "LECTURER";
  kode_surat: string;
  nama_surat: string;
  kategori: string;
  nomor_surat_resmi: string | null;
  status: SuratStatusCode;
  created_at: string;
}

export interface SuratRequestDetail {
  id: number;
  nim_mahasiswa: string;
  nama_mahasiswa: string;
  prodi_mahasiswa: string;
  fakultas_mahasiswa: string;
  requester_role?: "STUDENT" | "LECTURER";
  kode_surat: string;
  nama_surat: string;
  nomor_surat_resmi: string | null;
  status: SuratStatusCode;
  payload_data: Record<string, unknown>;
  user_prompt_context: string;
  ai_original_draft: string | null;
  final_approved_content: string | null;
  self_critique_score: number | null;
  revision_notes: string[] | string | null;
  file_pdf_url: string | null;
  qr_verification_code: string | null;
  signer_nama_override?: string | null;
  signer_nip_override?: string | null;
  chosen_destination?: "email" | "telegram" | null;
  target_destination_address?: string | null;
  attachments?: Array<{
    id: number;
    nama_dokumen: string;
    file_url: string;
    mime_type: string;
    created_at: string;
  }>;
  audit_logs?: Array<{
    id: number;
    action_id: string;
    action: string;
    created_at: string;
  }>;
  created_at: string;
  approvals: SuratApproval[];
}

export interface ChatThreadItem {
  thread_id: string;
  title: string;
  document_type: string | null;
  status: string;
  updated_at: string;
  created_at: string;
}

export interface ChatActionOption {
  label: string;
  value: string;
}

export interface ChatMessageItem {
  id: string;
  sender: "user" | "assistant" | "system";
  text: string;
  timestamp?: string;
  created_at?: string;
  slots_snapshot?: Record<string, unknown> | null;
}

export interface ChatSessionDetail {
  status: "success" | "ready_to_draft" | "error";
  state: string;
  is_ready_to_draft: boolean;
  action_required?: string | null;
  action_options?: ChatActionOption[];
  thread_id: string;
  title: string;
  intent?: string | null;
  kode_surat?: string | null;
  collected_slots?: Record<string, unknown>;
  missing_fields?: string[];
  messages: ChatMessageItem[];
  latest_surat_request?: SuratRequestDetail | null;
}

export interface NotificationItem {
  id: number;
  type: string;
  title: string;
  body: string;
  surat_request_id: number | null;
  is_read: boolean;
  created_at: string;
}

export interface VerificationData {
  status: "VALID" | "INVALID";
  message: string;
  detail_surat?: {
    nomor_surat_resmi: string | null;
    jenis_surat: string;
    kategori: string;
    tanggal_terbit: string;
  };
  mahasiswa?: {
    nim: string;
    nama: string;
    prodi: string;
    fakultas: string;
  };
  tte_info?: {
    hash_sha256: string;
    penandatangan: string;
    tanggal_ttd: string;
  };
}

export interface AiDraftItem {
  id: number;
  kode_surat: string;
  nama_surat: string;
  kategori: string;
  nomor_surat_resmi: string | null;
  status: SuratStatusCode;
  pemohon_nama: string;
  pemohon_identitas: string;
  pemohon_role: "STUDENT" | "LECTURER";
  prodi_nama: string;
  fakultas_nama: string;
  self_critique_score: number | null;
  payload_data: Record<string, unknown>;
  ai_original_draft: string;
  calibrated_draft: string | null;
  feedback_count: number;
  created_at: string;
}

export interface AiDraftGroup {
  kode_surat: string;
  nama_surat: string;
  kategori: string;
  active_rule_count: number;
  drafts: AiDraftItem[];
}

export interface AiDraftListResponse {
  categories: string[];
  groups: AiDraftGroup[];
}

export interface AiFeedbackMemoryItem {
  id: number;
  surat_request_id: number | null;
  kode_surat: string;
  nama_surat: string;
  diff_summary: string;
  extracted_rule: string;
  reference_draft: string | null;
  is_active: boolean;
  created_at: string;
}

export interface AiDraftFeedbackResponse {
  status: "learned" | "no_significant_change";
  learned: boolean;
  message: string;
  memory?: AiFeedbackMemoryItem;
}
