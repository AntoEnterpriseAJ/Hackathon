import { Injectable, computed, signal } from '@angular/core';

/** A single document that lives inside the Case. */
export type DocumentKind = 'fd' | 'plan' | 'template' | 'other';

export interface CaseDocument {
  id: string;
  name: string;
  kind: DocumentKind;
  /** Underlying file (kept in memory only — no upload until a tool needs it). */
  file: File;
  /** Optional cached parse result. */
  parsed?: unknown;
  /** Lightweight status flags shown as chips in the Explorer. */
  status: {
    parsed: boolean;
    validated: boolean;
  };
  addedAt: number;
}

/** A tab open in the main editor area. Either a document preview or a tool. */
export type TabKind =
  | { kind: 'document'; documentId: string }
  | { kind: 'tool'; tool: ToolKind; resultKey?: string };

export type ToolKind = 'diff' | 'sync' | 'migrate' | 'draft' | 'validate';

export interface CaseTab {
  id: string;
  title: string;
  icon: string;
  body: TabKind;
}

/** Mock edit proposal — single-field change rendered as a git diff. */
export interface EditProposal {
  field: string;          // e.g. "numar_credite" or "bibliografie[3]"
  oldValue: string;
  newValue: string;
  summary?: string;       // short human description
  status?: 'pending' | 'applied' | 'rejected';
}

/** Minimal chat message shape. Persistence is in-memory for v1. */
export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  /** Suggested follow-up questions (assistant messages only). */
  followups?: string[];
  /** Optional inline actions rendered as buttons next to the message. */
  actions?: ChatAction[];
  contextChips?: string[];
  /** Optional inline edit proposal rendered as a tiny git-diff card. */
  editProposal?: EditProposal;
  ts: number;
}

export type ChatAction =
  | { kind: 'open_tab'; tabId: string; label: string }
  | { kind: 'apply_patch'; label: string }; // stub in v1

/**
 * The Case is the single source of truth for everything the user is working
 * on. Every tool reads from and writes to this store via signals.
 */
@Injectable({ providedIn: 'root' })
export class CaseStore {
  // --- raw state ---------------------------------------------------------
  private readonly _documents = signal<CaseDocument[]>([]);
  private readonly _tabs = signal<CaseTab[]>([]);
  private readonly _activeTabId = signal<string | null>(null);
  private readonly _chat = signal<ChatMessage[]>([]);
  private readonly _toolResults = signal<Record<string, unknown>>({});
  /** Section id currently hovered in any tool — used for cross-tab highlight. */
  private readonly _highlightSectionId = signal<string | null>(null);

  // --- public read-only signals ------------------------------------------
  readonly documents = this._documents.asReadonly();
  readonly tabs = this._tabs.asReadonly();
  readonly activeTabId = this._activeTabId.asReadonly();
  readonly chat = this._chat.asReadonly();
  readonly toolResults = this._toolResults.asReadonly();
  readonly highlightSectionId = this._highlightSectionId.asReadonly();

  // --- derived -----------------------------------------------------------
  readonly activeTab = computed(() => {
    const id = this._activeTabId();
    return this._tabs().find((t) => t.id === id) ?? null;
  });

  readonly documentsByKind = computed(() => {
    const buckets: Record<DocumentKind, CaseDocument[]> = {
      fd: [],
      plan: [],
      template: [],
      other: [],
    };
    for (const d of this._documents()) {
      buckets[d.kind].push(d);
    }
    return buckets;
  });

  readonly hasAnyDocuments = computed(() => this._documents().length > 0);

  // --- document mutations ------------------------------------------------
  addDocument(file: File, kind: DocumentKind = 'other'): CaseDocument {
    const doc: CaseDocument = {
      id: cryptoId(),
      name: file.name,
      kind,
      file,
      status: { parsed: false, validated: false },
      addedAt: Date.now(),
    };
    this._documents.update((arr) => [...arr, doc]);
    return doc;
  }

  removeDocument(id: string): void {
    this._documents.update((arr) => arr.filter((d) => d.id !== id));
    // Close any tabs bound to this document.
    this._tabs.update((tabs) =>
      tabs.filter(
        (t) => !(t.body.kind === 'document' && t.body.documentId === id),
      ),
    );
  }

  updateDocument(id: string, patch: Partial<CaseDocument>): void {
    this._documents.update((arr) =>
      arr.map((d) => (d.id === id ? { ...d, ...patch } : d)),
    );
  }

  setDocumentStatus(
    id: string,
    patch: Partial<CaseDocument['status']>,
  ): void {
    this._documents.update((arr) =>
      arr.map((d) =>
        d.id === id ? { ...d, status: { ...d.status, ...patch } } : d,
      ),
    );
  }

  // --- tab mutations -----------------------------------------------------
  openDocumentTab(documentId: string): CaseTab {
    const existing = this._tabs().find(
      (t) => t.body.kind === 'document' && t.body.documentId === documentId,
    );
    if (existing) {
      this._activeTabId.set(existing.id);
      return existing;
    }
    const doc = this._documents().find((d) => d.id === documentId);
    if (!doc) {
      throw new Error(`Document not found: ${documentId}`);
    }
    const tab: CaseTab = {
      id: cryptoId(),
      title: doc.name,
      icon: iconForKind(doc.kind),
      body: { kind: 'document', documentId },
    };
    this._tabs.update((arr) => [...arr, tab]);
    this._activeTabId.set(tab.id);
    return tab;
  }

  openToolTab(tool: ToolKind, resultKey?: string): CaseTab {
    // Tools are singletons per case for now — re-opening focuses the existing tab.
    const existing = this._tabs().find(
      (t) => t.body.kind === 'tool' && t.body.tool === tool,
    );
    if (existing) {
      this._activeTabId.set(existing.id);
      return existing;
    }
    const tab: CaseTab = {
      id: cryptoId(),
      title: titleForTool(tool),
      icon: iconForTool(tool),
      body: { kind: 'tool', tool, resultKey },
    };
    this._tabs.update((arr) => [...arr, tab]);
    this._activeTabId.set(tab.id);
    return tab;
  }

  closeTab(tabId: string): void {
    const tabs = this._tabs();
    const idx = tabs.findIndex((t) => t.id === tabId);
    if (idx === -1) return;
    const next = [...tabs.slice(0, idx), ...tabs.slice(idx + 1)];
    this._tabs.set(next);
    if (this._activeTabId() === tabId) {
      const fallback = next[idx] ?? next[idx - 1] ?? null;
      this._activeTabId.set(fallback ? fallback.id : null);
    }
  }

  setActiveTab(tabId: string): void {
    if (this._tabs().some((t) => t.id === tabId)) {
      this._activeTabId.set(tabId);
    }
  }

  // --- chat --------------------------------------------------------------
  appendChat(msg: Omit<ChatMessage, 'id' | 'ts'>): ChatMessage {
    const m: ChatMessage = { ...msg, id: cryptoId(), ts: Date.now() };
    this._chat.update((arr) => [...arr, m]);
    return m;
  }

  /** Patch an existing chat message (e.g. mark a proposal applied/rejected). */
  updateChatMessage(id: string, patch: Partial<ChatMessage>): void {
    this._chat.update((arr) =>
      arr.map((m) => (m.id === id ? { ...m, ...patch } : m)),
    );
  }

  clearChat(): void {
    this._chat.set([]);
  }

  // --- tool results ------------------------------------------------------
  setToolResult(key: string, value: unknown): void {
    this._toolResults.update((r) => ({ ...r, [key]: value }));
  }

  getToolResult<T = unknown>(key: string): T | undefined {
    return this._toolResults()[key] as T | undefined;
  }

  // --- highlight ---------------------------------------------------------
  setHighlightSection(id: string | null): void {
    this._highlightSectionId.set(id);
  }
}

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------
function cryptoId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

function iconForKind(kind: DocumentKind): string {
  switch (kind) {
    case 'fd':
      return '📄';
    case 'plan':
      return '📕';
    case 'template':
      return '📐';
    default:
      return '📃';
  }
}

function iconForTool(tool: ToolKind): string {
  switch (tool) {
    case 'diff':
      return '🔍';
    case 'sync':
      return '🔗';
    case 'migrate':
      return '🔄';
    case 'draft':
      return '📝';
    case 'validate':
      return '✅';
  }
}

function titleForTool(tool: ToolKind): string {
  switch (tool) {
    case 'diff':
      return 'Diff';
    case 'sync':
      return 'Sync';
    case 'migrate':
      return 'Migrate';
    case 'draft':
      return 'Draft FD';
    case 'validate':
      return 'Validate';
  }
}

/**
 * Heuristic auto-classifier for document kind based on filename.
 * Real classification happens after parse via the backend, but we can give
 * the user immediate visual feedback while the parse is in flight.
 */
export function guessKindFromFilename(name: string): DocumentKind {
  const n = name.toLowerCase();
  if (n.includes('plan') || n.includes('pi_')) return 'plan';
  if (n.includes('template') || n.includes('shablon')) return 'template';
  if (
    n.includes('fd') ||
    n.includes('fisa') ||
    n.includes('fișa') ||
    n.includes('disciplin')
  ) {
    return 'fd';
  }
  return 'other';
}
