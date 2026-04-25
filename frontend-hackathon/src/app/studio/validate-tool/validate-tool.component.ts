import { Component, computed, effect, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { CaseStore, CaseDocument } from '../case.store';
import { SyncCheckService } from '../../sync-check/services/sync-check.service';
import {
  BibliographyReport,
  FdSliceResponse,
  NumericConsistencyReport,
  StructuralValidationResult,
} from '../../sync-check/models/sync.models';
import { forkJoin, switchMap } from 'rxjs';

interface ValidationResult {
  numeric: NumericConsistencyReport;
  biblio: BibliographyReport;
  structural: StructuralValidationResult;
}

function base64ToBlob(b64: string, type = 'application/pdf'): Blob {
  const bin = atob(b64);
  const arr = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
  return new Blob([arr], { type });
}

@Component({
  selector: 'app-validate-tool',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './validate-tool.component.html',
  styleUrl: './validate-tool.component.scss',
})
export class ValidateToolComponent {
  private readonly store = inject(CaseStore);
  private readonly service = inject(SyncCheckService);

  protected readonly fdId = signal<string | null>(null);
  protected readonly running = signal(false);
  protected readonly splitting = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly result = signal<ValidationResult | null>(null);

  /** Slices carved out of the picked FD bundle (one entry per discipline). */
  protected readonly slices = signal<FdSliceResponse[]>([]);
  /** Currently selected discipline within the bundle. */
  protected readonly sliceIndex = signal<number | null>(null);

  /** Per-FD-id cache of split results so flipping FDs doesn't re-split. */
  private readonly splitCache = new Map<string, FdSliceResponse[]>();

  protected readonly fdOptions = computed(() => this.store.documentsByKind().fd);

  protected readonly selectedSlice = computed<FdSliceResponse | null>(() => {
    const idx = this.sliceIndex();
    if (idx == null) return null;
    return this.slices().find((s) => s.index === idx) ?? null;
  });

  constructor() {
    queueMicrotask(() => {
      if (!this.fdId() && this.fdOptions()[0]) this.fdId.set(this.fdOptions()[0].id);
    });
    // Whenever the FD changes, kick off (or restore) the bundle split.
    effect(() => {
      const id = this.fdId();
      if (!id) {
        this.slices.set([]);
        this.sliceIndex.set(null);
        return;
      }
      this.loadSlicesFor(id);
    });
  }

  protected canRun(): boolean {
    return !!this.fdId() && !this.running() && !this.splitting();
  }

  protected onPickFd(e: Event): void {
    this.fdId.set((e.target as HTMLSelectElement).value || null);
    this.result.set(null);
    this.error.set(null);
  }

  protected onPickSlice(e: Event): void {
    const v = (e.target as HTMLSelectElement).value;
    this.sliceIndex.set(v === '' ? null : Number(v));
    this.result.set(null);
  }

  protected sliceLabel(s: FdSliceResponse): string {
    const hint = (s.course_name_hint ?? '').trim();
    const base = hint || `Disciplina #${s.index}`;
    return `${base} (p. ${s.page_start}–${s.page_end})`;
  }

  /** Load (or restore from cache) the per-discipline slices for this FD. */
  private loadSlicesFor(docId: string): void {
    const doc = this.store.documents().find((d) => d.id === docId);
    if (!doc) return;

    const cached = this.splitCache.get(docId);
    if (cached) {
      this.slices.set(cached);
      this.sliceIndex.set(cached[0]?.index ?? null);
      return;
    }

    const isPdf = /\.pdf$/i.test(doc.file.name) || doc.file.type === 'application/pdf';
    if (!isPdf) {
      const single: FdSliceResponse[] = [{
        index: 1,
        course_name_hint: doc.file.name,
        page_start: 1,
        page_end: 1,
        pdf_base64: '',
      }];
      this.splitCache.set(docId, single);
      this.slices.set(single);
      this.sliceIndex.set(1);
      return;
    }

    this.splitting.set(true);
    this.error.set(null);
    this.service.splitBundle(doc.file).subscribe({
      next: (resp) => {
        this.splitting.set(false);
        // Backend may return 0 slices for a single-discipline PDF; fall back
        // to a single synthetic slice that re-uses the original file.
        const slices: FdSliceResponse[] = resp.slices.length > 0 ? resp.slices : [{
          index: 1,
          course_name_hint: doc.file.name,
          page_start: 1,
          page_end: resp.total_pages || 1,
          pdf_base64: '',
        }];
        this.splitCache.set(docId, slices);
        if (this.fdId() === docId) {
          this.slices.set(slices);
          this.sliceIndex.set(slices[0].index);
        }
      },
      error: (err) => {
        this.splitting.set(false);
        this.error.set(err?.error?.detail || err?.message || 'Failed to split FD bundle');
      },
    });
  }

  /** Parse the currently selected slice (or the original file if no slice). */
  private parseSelected(doc: CaseDocument, slice: FdSliceResponse | null) {
    if (!slice || !slice.pdf_base64) {
      return this.service.parse(doc.file);
    }
    const blob = base64ToBlob(slice.pdf_base64);
    const safeHint = (slice.course_name_hint || `disciplina-${slice.index}`)
      .replace(/[^\w\-. ]+/g, '_')
      .slice(0, 80);
    return this.service.parseBlob(blob, `${safeHint}.pdf`);
  }

  protected run(): void {
    const fd = this.store.documents().find((d) => d.id === this.fdId());
    if (!fd) return;

    this.error.set(null);
    this.result.set(null);
    this.running.set(true);

    this.parseSelected(fd, this.selectedSlice())
      .pipe(
        switchMap((parsed) =>
          forkJoin({
            numeric: this.service.checkNumericConsistency(parsed),
            biblio: this.service.checkFdBibliography(parsed, {}),
            structural: this.service.validateStructure(parsed),
          }),
        ),
      )
      .subscribe({
        next: (res) => {
          this.running.set(false);
          this.result.set(res);
          this.store.setDocumentStatus(fd.id, { validated: true });
          this.store.setToolResult('validate', res);
        },
        error: (err) => {
          this.running.set(false);
          this.error.set(err?.error?.detail || err?.message || 'Validation failed');
        },
      });
  }

  protected score(): number | null {
    const r = this.result();
    if (!r) return null;
    const numericTotal = r.numeric.total_checks || 1;
    const numericPassed = r.numeric.passed;
    const biblioTotal = r.biblio.total_entries || 1;
    const biblioPassed = r.biblio.fresh_entries;
    const structuralTotal = Object.keys({
      denumirea_disciplinei: 1, titularul_activitatilor_de_curs: 1,
      titularul_activitatilor_de_seminar_laborator_proiect: 1,
      obiective_generale_ale_disciplinei: 1, competente_profesionale: 1,
      competente_transversale: 1, semestrul: 1, anul_de_studiu: 1,
      numar_credite: 1, tipul_de_evaluare: 1,
    }).length;
    const structuralPassed = structuralTotal - r.structural.violations.filter(v => v.code === 'field_required').length;
    const ratio =
      (numericPassed + biblioPassed + structuralPassed) /
      (numericTotal + biblioTotal + structuralTotal);
    return Math.round(ratio * 10 * 10) / 10;
  }
}
