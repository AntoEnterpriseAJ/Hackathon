import { Component, computed, effect, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { CaseStore, CaseDocument, EditPatch, EditProposal } from '../case.store';
import { SyncCheckService } from '../../sync-check/services/sync-check.service';
import { ExtractedDocument } from '../../sync-check/models/sync.models';

@Component({
  selector: 'app-chat-rail',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './chat-rail.component.html',
  styleUrl: './chat-rail.component.scss',
})
export class ChatRailComponent {
  protected readonly store = inject(CaseStore);
  private readonly http = inject(HttpClient);
  private readonly parser = inject(SyncCheckService);

  protected readonly draft = signal('');
  protected readonly collapsed = signal(false);
  protected readonly sending = signal(false);
  protected readonly parsing = signal(false);

  /** Document the user wants to talk about; null = no grounding. */
  protected readonly selectedDocId = signal<string | null>(null);

  protected readonly allDocs = computed(() => this.store.documents());

  protected readonly selectedDoc = computed<CaseDocument | null>(() => {
    const id = this.selectedDocId();
    return id ? this.store.documents().find((d) => d.id === id) ?? null : null;
  });

  constructor() {
    // Default selection: follow the active document tab; otherwise first doc.
    effect(() => {
      const tab = this.store.activeTab();
      const docs = this.store.documents();
      if (this.selectedDocId() && docs.some((d) => d.id === this.selectedDocId())) {
        return; // user already picked something valid
      }
      if (tab?.body.kind === 'document') {
        this.selectedDocId.set(tab.body.documentId);
      } else if (docs[0]) {
        this.selectedDocId.set(docs[0].id);
      } else {
        this.selectedDocId.set(null);
      }
    });
  }

  protected onPickDoc(e: Event): void {
    const v = (e.target as HTMLSelectElement).value;
    this.selectedDocId.set(v || null);
  }

  protected async send(): Promise<void> {
    const text = this.draft().trim();
    if (!text || this.sending()) return;

    const doc = this.selectedDoc();
    const ctxChip = doc ? `@${doc.name}` : null;

    this.store.appendChat({
      role: 'user',
      text,
      contextChips: ctxChip ? [ctxChip] : [],
    });
    this.draft.set('');
    this.sending.set(true);

    try {
      const documents: unknown[] = [];
      if (doc) {
        const parsed = await this.ensureParsed(doc);
        if (parsed) documents.push(this.condenseForChat(doc.id, parsed));
      }

      const resp = await firstValueFrom(
        this.http.post<{
          reply: string;
          followups?: string[];
          edit_proposal?: {
            summary: string;
            doc_id: string | null;
            patches: EditPatch[];
          } | null;
        }>('/api/documents/chat', {
          message: text,
          documents,
        }),
      );

      const editProposal: EditProposal | undefined = resp.edit_proposal
        ? {
            summary: resp.edit_proposal.summary,
            // Backend may return the parsed-doc id (preferred) or null.
            doc_id: resp.edit_proposal.doc_id || doc?.id || null,
            patches: resp.edit_proposal.patches ?? [],
            status: 'pending',
          }
        : undefined;

      this.store.appendChat({
        role: 'assistant',
        text: resp.reply,
        followups: (resp.followups ?? []).slice(0, 3),
        editProposal,
      });
    } catch (err: unknown) {
      const e = err as { error?: { detail?: string }; message?: string };
      this.store.appendChat({
        role: 'assistant',
        text: `⚠ Eroare: ${e?.error?.detail || e?.message || 'Chat failed'}`,
      });
    } finally {
      this.sending.set(false);
    }
  }

  /** Parse the doc on demand, caching the result on the case store. */
  private async ensureParsed(doc: CaseDocument): Promise<ExtractedDocument | null> {
    if (doc.parsed) return doc.parsed as ExtractedDocument;
    this.parsing.set(true);
    try {
      const parsed = await firstValueFrom(this.parser.parse(doc.file));
      this.store.updateDocument(doc.id, { parsed });
      this.store.setDocumentStatus(doc.id, { parsed: true });
      return parsed;
    } catch {
      return null;
    } finally {
      this.parsing.set(false);
    }
  }

  /**
   * Trim the parsed payload before sending to chat: drop very long list values
   * (bibliography especially) to a reasonable head so we don't burn tokens or
   * trip request-size limits.
   */
  private condenseForChat(docId: string, doc: ExtractedDocument): unknown {
    const MAX_LIST = 25;
    const fields = doc.fields.map((f) => {
      if (Array.isArray(f.value) && f.value.length > MAX_LIST) {
        return {
          ...f,
          value: [
            ...f.value.slice(0, MAX_LIST),
            `… (+${f.value.length - MAX_LIST} more entries omitted)`,
          ],
        };
      }
      return f;
    });
    return { id: docId, ...doc, fields };
  }

  protected quickAction(kind: 'explain' | 'improve' | 'summarize'): void {
    const doc = this.selectedDoc();
    const target = doc ? `documentul „${doc.name}”` : 'documentul activ';
    const map = {
      explain: `Explică pe scurt ${target}.`,
      improve: `Sugerează îmbunătățiri pentru ${target}.`,
      summarize: `Rezumă ${target} în 5 puncte.`,
    };
    this.draft.set(map[kind]);
  }

  protected onKey(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.send();
    }
  }

  /** Click a suggested follow-up chip → fill draft and immediately send. */
  protected pickFollowup(text: string): void {
    if (this.sending()) return;
    this.draft.set(text);
    this.send();
  }

  // --- edit-proposal handling -------------------------------------------

  /** Look up the current value of a field key in the doc the proposal targets. */
  protected oldValueFor(proposal: EditProposal, fieldKey: string): unknown {
    const docId = proposal.doc_id;
    if (!docId) return undefined;
    const doc = this.store.documents().find((d) => d.id === docId);
    const parsed = doc?.parsed as ExtractedDocument | undefined;
    const f = parsed?.fields.find((x) => x.key === fieldKey);
    return f?.value;
  }

  /** Render any value as a compact, single-line string for the diff card. */
  protected formatValue(v: unknown): string {
    if (v === undefined || v === null) return '—';
    if (Array.isArray(v)) {
      if (v.length === 0) return '[ ]';
      if (v.length === 1) return String(v[0]);
      return `[${v.length} elemente] ${String(v[0]).slice(0, 60)}…`;
    }
    if (typeof v === 'object') return JSON.stringify(v).slice(0, 120);
    const s = String(v);
    return s.length > 160 ? s.slice(0, 160) + '…' : s;
  }

  protected opLabel(op: string): string {
    return op === 'set' ? 'MODIFICĂ' : op === 'add' ? 'ADAUGĂ' : 'ȘTERGE';
  }

  /** Apply the proposal: POST to backend, swap parsed doc on the store. */
  protected async acceptProposal(messageId: string, proposal: EditProposal): Promise<void> {
    if (proposal.status !== 'pending') return;
    const docId = proposal.doc_id;
    const doc = docId ? this.store.documents().find((d) => d.id === docId) : null;
    if (!doc || !doc.parsed) {
      this.store.updateChat(messageId, {
        editProposal: { ...proposal, status: 'rejected' },
      });
      this.store.appendChat({
        role: 'assistant',
        text: '⚠ Nu am găsit documentul țintă pentru aceste modificări.',
      });
      return;
    }
    try {
      const resp = await firstValueFrom(
        this.http.post<{
          doc: ExtractedDocument;
          applied: EditPatch[];
          skipped: { patch: EditPatch; reason: string }[];
        }>('/api/documents/apply-patches', {
          doc: doc.parsed,
          patches: proposal.patches,
        }),
      );
      this.store.updateDocument(doc.id, { parsed: resp.doc });
      this.store.updateChat(messageId, {
        editProposal: { ...proposal, status: 'applied' },
      });
      const skippedNote = resp.skipped.length
        ? ` (${resp.skipped.length} ignorate: ${resp.skipped.map((s) => s.reason).join(', ')})`
        : '';
      this.store.appendChat({
        role: 'assistant',
        text: `✓ Am aplicat ${resp.applied.length} modificare/i pe „${doc.name}”.${skippedNote}`,
      });
    } catch (err: unknown) {
      const e = err as { error?: { detail?: string }; message?: string };
      this.store.appendChat({
        role: 'assistant',
        text: `⚠ Nu am putut aplica modificările: ${e?.error?.detail || e?.message || 'eroare'}`,
      });
    }
  }

  protected rejectProposal(messageId: string, proposal: EditProposal): void {
    if (proposal.status !== 'pending') return;
    this.store.updateChat(messageId, {
      editProposal: { ...proposal, status: 'rejected' },
    });
  }

  /**
   * Minimal, safe markdown renderer for assistant replies.
   * Escapes HTML, then applies: **bold**, *italic*, `code`, paragraph breaks,
   * and basic - / 1. lists. No raw HTML, no links — sufficient for our use.
   */
  protected renderMarkdown(text: string): string {
    if (!text) return '';
    const escaped = text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');

    // Inline formatting (run before block parsing so it works inside list items).
    const inline = (s: string): string =>
      s
        .replace(/`([^`\n]+)`/g, '<code>$1</code>')
        .replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
        .replace(/(^|[\s(])\*([^*\n]+)\*/g, '$1<em>$2</em>');

    // Block parsing: group consecutive list items, separate paragraphs by blank lines.
    const lines = escaped.split(/\r?\n/);
    const out: string[] = [];
    let listKind: 'ul' | 'ol' | null = null;
    let para: string[] = [];

    const flushPara = () => {
      if (para.length) {
        out.push('<p>' + inline(para.join(' ')) + '</p>');
        para = [];
      }
    };
    const flushList = () => {
      if (listKind) {
        out.push(`</${listKind}>`);
        listKind = null;
      }
    };

    for (const raw of lines) {
      const line = raw.trimEnd();
      const ulMatch = /^\s*[-*•]\s+(.*)$/.exec(line);
      const olMatch = /^\s*\d+[.)]\s+(.*)$/.exec(line);
      if (ulMatch) {
        flushPara();
        if (listKind !== 'ul') { flushList(); out.push('<ul>'); listKind = 'ul'; }
        out.push('<li>' + inline(ulMatch[1]) + '</li>');
      } else if (olMatch) {
        flushPara();
        if (listKind !== 'ol') { flushList(); out.push('<ol>'); listKind = 'ol'; }
        out.push('<li>' + inline(olMatch[1]) + '</li>');
      } else if (!line.trim()) {
        flushPara();
        flushList();
      } else {
        flushList();
        para.push(line);
      }
    }
    flushPara();
    flushList();
    return out.join('');
  }

  protected toggleCollapse(): void {
    this.collapsed.update((c) => !c);
  }
}
