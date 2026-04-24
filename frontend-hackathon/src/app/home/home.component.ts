import { Component } from '@angular/core';

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

import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-home',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './home.component.html',
  styleUrl: './home.component.scss'
})
export class HomeComponent {
  acceptedTypes = '.pdf,.png,.jpg,.jpeg,.tif,.tiff,.bmp';
  prompt = '';
  isDragging = false;

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

  sendMessage(): void {
    const text = this.prompt.trim();
    if (!text) {
      return;
    }

    this.messages = [...this.messages, this.createMessage('teacher', text)];
    this.prompt = '';

    const response = this.composeAssistantReply(text);
    this.messages = [...this.messages, this.createMessage('assistant', response)];
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
    }

    if (accepted.length) {
      this.messages = [
        ...this.messages,
        this.createMessage(
          'assistant',
          `Loaded ${accepted.length} document${accepted.length > 1 ? 's' : ''}: ${accepted.join(', ')}. I can now extract fields, summarize key points, and draft your paperwork.`
        )
      ];
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

  private composeAssistantReply(userText: string): string {
    const lower = userText.toLowerCase();
    const documentSummary = this.documents.length
      ? `I will use ${this.documents.length} uploaded file${this.documents.length > 1 ? 's' : ''}: ${this.documents
        .slice(0, 3)
        .map((doc) => doc.name)
        .join(', ')}${this.documents.length > 3 ? ', and more' : ''}.`
      : 'No files are uploaded yet. Please add a PDF or scanned document first so I can extract details accurately.';

    let workflow =
      'Paperwork plan:\n1. Extract names, dates, and obligations\n2. Draft a clean summary for records\n3. Generate next-step checklist with due dates';

    if (lower.includes('iep') || lower.includes('accommodation')) {
      workflow =
        'IEP support plan:\n1. Capture each accommodation request\n2. Align requests to classroom actions\n3. Produce parent-ready summary and implementation checklist';
    }

    if (lower.includes('attendance') || lower.includes('absence')) {
      workflow =
        'Attendance workflow:\n1. Extract dates and reason codes\n2. Draft attendance follow-up note\n3. Create office submission checklist';
    }

    if (lower.includes('parent') || lower.includes('guardian')) {
      workflow =
        'Family communication draft:\n1. Summarize the document in plain language\n2. Flag required signatures or responses\n3. Prepare a concise parent message and internal log note';
    }

    return `${documentSummary}\n\nRequested task: "${userText}"\n\n${workflow}`;
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
