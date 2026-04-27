import { Component, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { CaseStore } from '../case.store';
import { DiffService } from '../../diff/services/diff.service';
import { DiffResponse, LogicChange, DiffNarrative } from '../../diff/models/diff.models';

@Component({
  selector: 'app-diff-tool',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './diff-tool.component.html',
  styleUrl: './diff-tool.component.scss',
})
export class DiffToolComponent {
  private readonly store = inject(CaseStore);
  private readonly service = inject(DiffService);

  protected readonly oldId = signal<string | null>(null);
  protected readonly newId = signal<string | null>(null);
  protected readonly parserType = signal<'fd' | 'pi'>('fd');
  protected readonly running = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly result = signal<DiffResponse | null>(null);

  protected readonly narrative = signal<DiffNarrative | null>(null);
  protected readonly explaining = signal(false);
  protected readonly narrativeError = signal<string | null>(null);

  protected readonly fdOptions = computed(() => this.store.documentsByKind().fd);
  protected readonly planOptions = computed(() => this.store.documentsByKind().plan);

  protected readonly options = computed(() =>
    this.parserType() === 'fd' ? this.fdOptions() : this.planOptions(),
  );

  constructor() {
    queueMicrotask(() => {
      const opts = this.options();
      if (!this.oldId() && opts[0]) this.oldId.set(opts[0].id);
      if (!this.newId() && opts[1]) this.newId.set(opts[1].id);
    });
  }

  protected canRun(): boolean {
    return (
      !!this.oldId() &&
      !!this.newId() &&
      this.oldId() !== this.newId() &&
      !this.running()
    );
  }

  protected onPickOld(e: Event): void {
    this.oldId.set((e.target as HTMLSelectElement).value || null);
  }
  protected onPickNew(e: Event): void {
    this.newId.set((e.target as HTMLSelectElement).value || null);
  }
  protected onPickParser(e: Event): void {
    const v = (e.target as HTMLSelectElement).value as 'fd' | 'pi';
    this.parserType.set(v);
    // reset selections to first two of new bucket
    this.oldId.set(null);
    this.newId.set(null);
    queueMicrotask(() => {
      const opts = this.options();
      if (opts[0]) this.oldId.set(opts[0].id);
      if (opts[1]) this.newId.set(opts[1].id);
    });
  }

  protected run(): void {
    const oldDoc = this.store.documents().find((d) => d.id === this.oldId());
    const newDoc = this.store.documents().find((d) => d.id === this.newId());
    if (!oldDoc || !newDoc) return;

    this.error.set(null);
    this.result.set(null);
    this.narrative.set(null);
    this.narrativeError.set(null);
    this.running.set(true);

    this.service.compare(oldDoc.file, newDoc.file, this.parserType()).subscribe({
      next: (res) => {
        this.running.set(false);
        this.result.set(res);
        this.store.setToolResult('diff', res);
      },
      error: (err) => {
        this.running.set(false);
        this.error.set(
          err?.error?.detail || err?.message || 'Diff failed (is diff service on :5000?)',
        );
      },
    });
  }

  protected severityClass(c: LogicChange): string {
    return 'sev-' + c.severity.toLowerCase();
  }

  protected explain(): void {
    const r = this.result();
    if (!r || this.explaining()) return;
    this.narrativeError.set(null);
    this.narrative.set(null);
    this.explaining.set(true);
    this.service.explainDiff(r).subscribe({
      next: (n) => {
        this.explaining.set(false);
        this.narrative.set(n);
      },
      error: (err) => {
        this.explaining.set(false);
        this.narrativeError.set(
          err?.error?.detail || err?.message || 'Explain failed',
        );
      },
    });
  }

  protected readonly showUnchanged = signal(false);

  protected toggleUnchanged(e: Event): void {
    this.showUnchanged.set((e.target as HTMLInputElement).checked);
  }

  protected visibleSections() {
    const r = this.result();
    if (!r) return [];
    return this.showUnchanged()
      ? r.sections
      : r.sections.filter((s) => s.status !== 'equal');
  }

  protected countAdds(s: { lines: { type: string }[] }): number {
    return s.lines.filter((l) => l.type === 'add' || l.type === 'replace').length;
  }
  protected countRemoves(s: { lines: { type: string }[] }): number {
    return s.lines.filter((l) => l.type === 'remove' || l.type === 'replace').length;
  }

  /** Flatten LineDiff into per-row entries (replace becomes a remove + add pair). */
  protected expandLines(
    lines: import('../../diff/models/diff.models').LineDiff[],
  ): Array<{
    kind: 'equal' | 'add' | 'remove';
    sigil: string;
    text: string;
    oldNo: number | null;
    newNo: number | null;
    inline?: import('../../diff/models/diff.models').InlineDiff[] | null;
  }> {
    const out: ReturnType<typeof this.expandLines> = [];
    for (const ln of lines) {
      if (ln.type === 'equal') {
        out.push({
          kind: 'equal',
          sigil: ' ',
          text: ln.old_text ?? ln.new_text ?? '',
          oldNo: ln.old_line_no,
          newNo: ln.new_line_no,
        });
      } else if (ln.type === 'add') {
        out.push({
          kind: 'add',
          sigil: '+',
          text: ln.new_text ?? '',
          oldNo: null,
          newNo: ln.new_line_no,
        });
      } else if (ln.type === 'remove') {
        out.push({
          kind: 'remove',
          sigil: '-',
          text: ln.old_text ?? '',
          oldNo: ln.old_line_no,
          newNo: null,
        });
      } else if (ln.type === 'replace') {
        const inline = ln.inline_diff ?? null;
        out.push({
          kind: 'remove',
          sigil: '-',
          text: ln.old_text ?? '',
          oldNo: ln.old_line_no,
          newNo: null,
          inline: inline?.filter((s) => s.type !== 'add'),
        });
        out.push({
          kind: 'add',
          sigil: '+',
          text: ln.new_text ?? '',
          oldNo: null,
          newNo: ln.new_line_no,
          inline: inline?.filter((s) => s.type !== 'remove'),
        });
      }
    }
    return out;
  }
}
