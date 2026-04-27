import { Component, computed, effect, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { CaseStore, CaseDocument, EditProposal } from '../case.store';
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
        if (parsed) documents.push(this.condenseForChat(parsed));
      }

      const resp = await firstValueFrom(
        this.http.post<{ reply: string; followups?: string[] }>('/api/documents/chat', {
          message: text,
          documents,
        }),
      );
      // MOCK: detect Romanian/English edit-intent verbs and synthesize a
      // tiny edit-proposal so we can render the git-diff card. Pure UI mock —
      // no patches are actually applied.
      const editProposal = this.maybeMockEditProposal(text, doc);
      this.store.appendChat({
        role: 'assistant',
        text: editProposal ? '' : resp.reply,
        followups: editProposal ? [] : (resp.followups ?? []).slice(0, 3),
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
  private condenseForChat(doc: ExtractedDocument): unknown {
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
    return { ...doc, fields };
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

  // ---------------------------------------------------------------------------
  // Mock edit-proposal (UI-only, no backend wiring yet)
  // ---------------------------------------------------------------------------

  /**
   * Detect simple "schimbă X la Y" / "change X to Y" patterns and synthesize
   * a fake EditProposal so we can demo the inline git-diff card without the
   * backend tool yet. Returns undefined when the message doesn't look like an
   * edit request.
   */
  private maybeMockEditProposal(
    userText: string,
    doc: CaseDocument | null,
  ): EditProposal | undefined {
    const verbs = /(schimb[ăa]|modific[ăa]|actualizeaz[ăa]|redenume[șs]te|change|update|set|rename)/i;
    if (!verbs.test(userText)) return undefined;

    // Pattern A: "<verb> ... <field>: <old> (la|to|în) <new>"  (colon form)
    // Pattern B: "<verb> ... <field-phrase> (la|to|în) <new>"   (no old value given)
    const colonMatch =
      /(?:schimb[ăa]|modific[ăa]|actualizeaz[ăa]|redenume[șs]te|change|update|set|rename)\s+(?:.*?\b)?([a-zăâîșț_][\w ăâîșț_-]{1,80}?)\s*[:\-—]\s*(.+?)\s+(?:la|to|=>?|[îi]n)\s+(.+?)\s*\.?$/iu.exec(
        userText,
      );
    const plainMatch = colonMatch ? null :
      /(?:schimb[ăa]|modific[ăa]|actualizeaz[ăa]|redenume[șs]te|change|update|set|rename)\s+(?:.*?\b)?([a-zăâîșț_][\w ăâîșț_-]{1,80}?)\s+(?:la|to|=>?|[îi]n)\s+(.+?)\s*\.?$/iu.exec(
        userText,
      );

    const fieldPhrase = ((colonMatch?.[1] ?? plainMatch?.[1]) ?? 'numar_credite')
      .trim().toLowerCase();
    const oldFromText = colonMatch?.[2]?.trim().replace(/^["„]|["”]$/g, '') ?? '';
    const newValue = ((colonMatch?.[3] ?? plainMatch?.[2]) ?? '5')
      .trim().replace(/^["„]|["”]$/g, '');

    // Map common phrases → canonical field name. First match wins.
    const phraseAlias: { test: RegExp; field: string }[] = [
      { test: /(nume|name|denumire).*(curs|course|discipli|materi)/, field: 'nume_disciplina' },
      { test: /(curs|course|discipli|materi).*(nume|name|denumire)/, field: 'nume_disciplina' },
      { test: /^(nume|name|denumire|curs|course|discipli|materi)/, field: 'nume_disciplina' },
      { test: /(num[ăa]r.*credit|^credite$|^credits$)/, field: 'numar_credite' },
      { test: /titular.*(curs|course)/, field: 'titular_curs' },
      { test: /titular.*seminar/, field: 'titular_seminar' },
      { test: /(semestr|semester)/, field: 'semestru' },
    ];
    let field = fieldPhrase.replace(/\s+/g, '_');
    for (const a of phraseAlias) {
      if (a.test.test(fieldPhrase)) { field = a.field; break; }
    }

    // Prefer explicit old value from text; otherwise look it up in the parsed doc.
    let oldValue = oldFromText;
    if (!oldValue) {
      const parsed = doc?.parsed as { fields?: { name?: string; value?: unknown }[] } | undefined;
      const found = parsed?.fields?.find((f) => (f.name ?? '').toLowerCase() === field);
      if (found && found.value != null) {
        oldValue = Array.isArray(found.value)
          ? `[${found.value.length} entries]`
          : String(found.value);
      }
    }

    return {
      field,
      oldValue,
      newValue,
      summary: `Modificare propusă pentru "${field}"`,
    };
  }

  protected acceptProposal(msgId: string, proposal: EditProposal): void {
    this.store.updateChatMessage(msgId, {
      editProposal: { ...proposal, status: 'applied' },
    });
  }

  protected rejectProposal(msgId: string, proposal: EditProposal): void {
    this.store.updateChatMessage(msgId, {
      editProposal: { ...proposal, status: 'rejected' },
    });
  }
}
