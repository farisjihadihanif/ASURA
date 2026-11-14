import api from './api';
import type {
  SuratType,
  SuratRequestListItem,
  SuratRequestDetail,
  ChatThreadItem,
  ChatSessionDetail,
  NotificationItem,
  VerificationData,
} from '../types';
export const suratService = {
  async getSuratTypes(): Promise<SuratType[]> {
    const res = await api.get<SuratType[]>('/api/surat/types/');
    return Array.isArray(res.data) ? res.data : [];
  },
  async initChat(title = 'Permohonan Surat Baru', documentType: string | null = null) {
    const res = await api.post('/api/surat/chat/init/', {
      title,
      document_type: documentType,
    });
    return res.data as { thread_id: string; title: string; initial_message?: string };
  },
  async getChatThreads(): Promise<ChatThreadItem[]> {
    const res = await api.get<ChatThreadItem[]>('/api/surat/chat/threads/');
    return Array.isArray(res.data) ? res.data : [];
  },
  async deleteChatThread(threadId: string): Promise<void> {
    await api.delete(`/api/surat/chat/${threadId}/`);
  },
  async getChatSession(threadId: string): Promise<ChatSessionDetail> {
    const res = await api.get<ChatSessionDetail>(`/api/surat/chat/${threadId}/`);
    return res.data;
  },
  async sendChatMessage(threadId: string, message: string, attachments?: File[]) {
    if (attachments && attachments.length > 0) {
      const formData = new FormData();
      formData.append('message', message);
      attachments.forEach((f) => formData.append('attachments', f));
      const res = await api.post(`/api/surat/chat/${threadId}/`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      return res.data;
    }
    const res = await api.post(`/api/surat/chat/${threadId}/`, { message });
    return res.data;
  },
  async createSuratRequest(params: {
    kode_surat: string;
    user_prompt_context: string;
    payload_data?: Record<string, unknown>;
    thread_id?: string;
  }) {
    const res = await api.post('/api/surat/request/', params);
    return res.data;
  },
  async getSuratRequests(): Promise<SuratRequestListItem[]> {
    const res = await api.get<SuratRequestListItem[]>('/api/surat/requests/');
    return Array.isArray(res.data) ? res.data : [];
  },
  async getSuratRequestDetail(id: number): Promise<SuratRequestDetail> {
    const res = await api.get<SuratRequestDetail>(`/api/surat/requests/${id}/`);
    return res.data;
  },
  async fetchPdfBlobUrl(requestId: number): Promise<string> {
    const res = await api.get<{ pdf_base64: string; filename?: string }>(
      `/api/surat/requests/${requestId}/preview-pdf/`,
      { params: { encoding: 'base64' } }
    );
    const b64 = res.data?.pdf_base64 || '';
    const binaryStr = window.atob(b64);
    const bytes = new Uint8Array(binaryStr.length);
    for (let i = 0; i < binaryStr.length; i++) {
      bytes[i] = binaryStr.charCodeAt(i);
    }
    const pdfBlob = new Blob([bytes], { type: 'application/pdf' });
    return URL.createObjectURL(pdfBlob);
  },
  async submitApprovalAction(
    approvalId: number,
    params: {
      action: 'APPROVE' | 'REJECT' | 'REVISION_REQUIRED';
      catatan?: string;
      final_approved_content?: string;
      alasan_penolakan?: string;
      signer_nama?: string;
      signer_nip?: string;
      save_to_profile?: boolean;
      signature_mode?: 'qr' | 'manual_image';
      signature_image?: File | null;
    }
  ) {
    if (params.signature_mode === 'manual_image' && params.signature_image) {
      const formData = new FormData();
      formData.append('action', params.action);
      if (params.catatan) formData.append('catatan', params.catatan);
      if (params.final_approved_content) formData.append('final_approved_content', params.final_approved_content);
      if (params.alasan_penolakan) formData.append('alasan_penolakan', params.alasan_penolakan);
      if (params.signer_nama) formData.append('signer_nama', params.signer_nama);
      if (params.signer_nip) formData.append('signer_nip', params.signer_nip);
      if (params.save_to_profile) formData.append('save_to_profile', 'true');
      formData.append('signature_mode', 'manual_image');
      formData.append('signature_image', params.signature_image);
      const res = await api.post(`/api/surat/approval/${approvalId}/action/`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      return res.data;
    }
    const res = await api.post(`/api/surat/approval/${approvalId}/action/`, params);
    return res.data;
  },
  async deliverSuratEmail(requestId: number, recipientEmail: string) {
    const res = await api.post(`/api/surat/requests/${requestId}/deliver-email/`, {
      recipient_email: recipientEmail,
    });
    return res.data;
  },
  async markSuratPrinted(requestId: number) {
    const res = await api.post(`/api/surat/requests/${requestId}/mark-printed/`, {});
    return res.data;
  },
  async getNotifications(): Promise<NotificationItem[]> {
    const res = await api.get<NotificationItem[]>('/api/surat/notifications/');
    return Array.isArray(res.data) ? res.data : [];
  },
  async getUnreadNotificationCount(): Promise<number> {
    const res = await api.get<{ count: number }>('/api/surat/notifications/unread-count/');
    return res.data?.count || 0;
  },
  async markNotificationRead(id: number) {
    await api.post(`/api/surat/notifications/${id}/read/`, {});
  },
  async markAllNotificationsRead() {
    await api.post('/api/surat/notifications/read-all/', {});
  },
  async verifySurat(token: string): Promise<VerificationData> {
    const res = await api.get<VerificationData>(`/api/surat/verify/${token}/`);
    return res.data;
  },
};
export default suratService;


