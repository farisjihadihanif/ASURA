D:\coolyeah\ASURA\
├── README.md
├── run-web.ps1
├── run-local.ps1
├── backend-django/
│ ├── sync_base_backend.py <-- Otomatis menyalin inti Django & Agent AI dari proyek acuan lama
│ ├── surat/
│ │ ├── models.py
│ │ ├── serializers.py
│ │ ├── urls.py
│ │ ├── views.py
│ │ ├── migrations/
│ │ │ └── 0011_asura_chat_and_manual_signature.py
│ │ ├── services/
│ │ │ └── workflow_service.py
│ │ └── agents/
│ │ └── execution_tools.py
│ └── templates/
│ └── kerangka-surat/
│ └── base_surat.html
├── frontend/ <-- Tetap memakai UI asli ASURA (#fffdfa / #fbf5f0 / #d76b3e)
│ ├── package.json
│ ├── tsconfig.json
│ ├── tsconfig.app.json
│ ├── tsconfig.node.json
│ ├── vite.config.ts
│ ├── index.html
│ ├── public/
│ │ └── favicon.svg
│ └── src/
│ ├── main.tsx
│ ├── index.css
│ ├── App.tsx
│ ├── types/
│ │ └── index.ts
│ ├── services/
│ │ ├── api.ts
│ │ ├── authService.ts
│ │ └── suratService.ts
│ ├── context/
│ │ └── AuthContext.tsx
│ ├── components/
│ │ ├── ProtectedRoute.tsx
│ │ ├── NotificationBell.tsx
│ │ ├── StudentSidebar.tsx
│ │ ├── LecturerSidebar.tsx
│ │ ├── SuratActionCard.tsx
│ │ └── PdfPreviewModal.tsx
│ └── pages/
│ ├── LoginPage.tsx
│ ├── StudentChatPage.tsx
│ ├── LecturerApprovalsPage.tsx
│ └── VerifySuratPage.tsx
└── desktop-app/ <-- Aplikasi Windows Electron (Maskot Email + Pop-up Chat)
├── package.json
├── main.js
├── preload.js
├── index.html
├── styles.css
├── renderer.js
└── assets/
└── asura-mascot.png
