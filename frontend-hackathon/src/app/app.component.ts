import { Component, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';

type MessageRole = 'teacher' | 'assistant' | 'system';

interface ChatMessage {
  id: number;
  role: MessageRole;
  content: string;
  timestamp: Date;
}

interface UploadedDocument {
  id: number;
  name: string;
  sizeLabel: string;
  typeLabel: string;
  uploadedAt: Date;
}

@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrl: './app.component.scss'
})
export class AppComponent {
  private readonly http = inject(HttpClient);
  private readonly apiUrl = '/api';

  acceptedTypes = '.pdf,.png,.jpg,.jpeg,.tif,.tiff,.bmp';
  prompt = '';
  isDragging = false;

  /** Stores extracted document data for use in chat context. */
  parsedDocuments: ParsedDocument[] = [];
  isChatLoading = false;

  quickActions = [
    'Draft a parent communication summary from these files',
    'Extract student accommodation requests from uploaded forms',
    'Build a checklist for this week\'s paperwork deadlines',
    'Create an action list for admin follow-up'
  ];

  formatHints = [
    'PDF worksheets and forms',
    'Scanned pages (JPG, PNG, TIFF)',
    'Signed slips and handwritten notes'
  ];

  documents: UploadedDocument[] = [];

  private nextMessageId = 1;
  private nextDocumentId = 1;
  private readonly maxFileSizeBytes = 20 * 1024 * 1024;
  private readonly allowedMimeTypes = new Set([
    'application/pdf',
    'image/png',
    'image/jpeg',
    'image/tiff',
    'image/bmp'
  ]);

  messages: ChatMessage[] = [
    this.createMessage(
      'assistant',
      'Teacher Desk is ready. Upload your PDF or scanned documents, then tell me what paperwork you want to complete.'
    )
  ];

  handlePromptChange(event: Event): void {
    const target = event.target as HTMLTextAreaElement;
    this.prompt = target.value;
  }

  handlePromptKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.sendMessage();
    }
  }

  useQuickAction(action: string): void {
    this.prompt = action;
    this.sendMessage();
  }

  onFileSelection(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.ingestFiles(input.files);
    input.value = '';
  }

  onDragOver(event: DragEvent): void {
    event.preventDefault();
    this.isDragging = true;
  }

  onDragLeave(event: DragEvent): void {
    event.preventDefault();
    this.isDragging = false;
  }

  onDrop(event: DragEvent): void {
    event.preventDefault();
    this.isDragging = false;
    this.ingestFiles(event.dataTransfer?.files ?? null);
  }

  private parseFileWithBackend(file: File): void {
    const formData = new FormData();
    formData.append('file', file);

    this.messages = [
      ...this.messages,
      this.createMessage('system', `Parsing ${file.name}\u2026`),
    ];

    this.http
      .post<ParsedDocument>(`${this.apiUrl}/documents/parse`, formData)
      .subscribe({
        next: (result) => {
          this.parsedDocuments.push(result);
          this.messages = [
            ...this.messages,
            this.createMessage('assistant', this.formatParsedDoc(result, file.name)),
          ];
        },
        error: (err) => {
          const detail = this.toHttpErrorDetail(err);
          this.messages = [
            ...this.messages,
            this.createMessage('system', `Parse error for ${file.name}: ${detail}`),
          ];
        },
      });
  }

  private formatParsedDoc(doc: ParsedDocument, filename: string): string {
    const fieldLines = doc.fields
      .map((f) => {
        const val = f.value == null
          ? (f.field_type === 'signature' ? 'Pending signature' : 'Not provided')
          : Array.isArray(f.value)
            ? f.value.join(', ')
            : String(f.value);
        const flag = f.confidence !== 'high' ? ` [${f.confidence}]` : '';
        const sigTag = f.field_type === 'signature' ? ' \u2710' : '';
        return `\u2022 ${f.key.replace(/_/g, ' ')}: ${val}${flag}${sigTag}`;
      })
      .join('\n');

    let msg = `${doc.document_type.replace(/_/g, ' ').toUpperCase()} \u2014 ${filename}\n\n${doc.summary}`;
    if (fieldLines) {
      msg += `\n\nExtracted fields:\n${fieldLines}`;
    }
    if (doc.tables.length > 0) {
      const tableNames = doc.tables.map((t) => t.name).join(', ');
      msg += `\n\n${doc.tables.length} table(s): ${tableNames}.`;
    }
    return msg;
  }

  sendMessage(): void {
    const text = this.prompt.trim();
    if (!text) {
      return;
    }

    this.messages = [...this.messages, this.createMessage('teacher', text)];
    this.prompt = '';
    this.isChatLoading = true;

    this.http
      .post<{ reply: string }>(`${this.apiUrl}/documents/chat`, {
        message: text,
        documents: this.parsedDocuments,
      })
      .subscribe({
        next: (res) => {
          this.isChatLoading = false;
          this.messages = [...this.messages, this.createMessage('assistant', res.reply)];
        },
        error: (err) => {
          this.isChatLoading = false;
          const detail = this.toHttpErrorDetail(err);
          this.messages = [
            ...this.messages,
            this.createMessage('system', `Chat error: ${detail}`),
          ];
        },
      });
  }

  formatTime(date: Date): string {
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  private ingestFiles(fileList: FileList | null): void {
    if (!fileList || fileList.length === 0) {
      return;
    }

    const accepted: string[] = [];
    const rejected: string[] = [];

    for (const file of Array.from(fileList)) {
      if (!this.isAllowedFileType(file)) {
        rejected.push(`${file.name} (unsupported file format)`);
        continue;
      }

      if (file.size > this.maxFileSizeBytes) {
        rejected.push(`${file.name} (exceeds 20MB limit)`);
        continue;
      }

      this.documents = [
        ...this.documents,
        {
          id: this.nextDocumentId++,
          name: file.name,
          sizeLabel: this.toSizeLabel(file.size),
          typeLabel: this.toTypeLabel(file),
          uploadedAt: new Date()
        }
      ];
      accepted.push(file.name);
      this.parseFileWithBackend(file);
    }

    if (rejected.length) {
      this.messages = [
        ...this.messages,
        this.createMessage('system', `Could not process: ${rejected.join('; ')}`)
      ];
    }
  }

  private isAllowedFileType(file: File): boolean {
    return this.allowedMimeTypes.has(file.type) || /\.(pdf|png|jpe?g|tif|tiff|bmp)$/i.test(file.name);
  }

  private toTypeLabel(file: File): string {
    if (file.type === 'application/pdf' || /\.pdf$/i.test(file.name)) {
      return 'PDF';
    }

    if (/\.(tif|tiff)$/i.test(file.name) || file.type === 'image/tiff') {
      return 'Scanned TIFF';
    }

    if (/\.(jpg|jpeg)$/i.test(file.name)) {
      return 'Scanned JPG';
    }

    if (/\.png$/i.test(file.name)) {
      return 'Scanned PNG';
    }

    return 'Document';
  }

  private toHttpErrorDetail(err: { status?: number; statusText?: string; error?: unknown }): string {
    if (typeof err?.error === 'object' && err.error && 'detail' in err.error) {
      const detail = (err.error as { detail?: unknown }).detail;
      if (typeof detail === 'string' && detail.trim()) {
        return detail;
      }
    }

    if (err?.status) {
      return `HTTP ${err.status}: ${err.statusText}`;
    }

    return 'No response from API. Confirm ng serve was restarted and the FastAPI server is running on 127.0.0.1:8000.';
  }

  private toSizeLabel(bytes: number): string {
    if (bytes < 1024 * 1024) {
      return `${Math.max(1, Math.round(bytes / 1024))} KB`;
    }

    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  private createMessage(role: MessageRole, content: string): ChatMessage {
    return {
      id: this.nextMessageId++,
      role,
      content,
      timestamp: new Date()
    };
  }
}

interface ParsedDocument {
  document_type: string;
  summary: string;
  fields: ExtractedField[];
  tables: ExtractedTable[];
  source_route: string;
}

interface ExtractedField {
  key: string;
  value: string | number | boolean | string[] | null;
  field_type: 'string' | 'date' | 'number' | 'boolean' | 'list' | 'signature' | 'id';
  confidence: 'high' | 'medium' | 'low';
}

interface ExtractedTable {
  name: string;
  headers: string[];
  rows: string[][];
}
