import { Component, computed, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { catchError, firstValueFrom, of } from 'rxjs';

import { SyncCheckService } from '../services/sync-check.service';
import {
  BibliographyReport,
  CompetencyMapping,
  CrossValidationResult,
  ExtractedDocument,
  FdSliceResponse,
  NumericConsistencyReport,
} from '../models/sync.models';

type Status = 'idle' | 'splitting' | 'parsing' | 'validating' | 'done' | 'error';

interface SliceRun {
  status: 'pending' | 'running' | 'done' | 'error';
  result?: CrossValidationResult;
  fdRoute?: string;
  competencyMapping?: CompetencyMapping;
  competencyError?: string;
  numericReport?: NumericConsistencyReport;
  numericError?: string;
  bibliographyReport?: BibliographyReport;
  bibliographyError?: string;
  error?: string;
}

function base64ToBlob(b64: string, type = 'application/pdf'): Blob {
  const bin = atob(b64);
  const arr = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
  return new Blob([arr], { type });
}

@Component({
  selector: 'app-sync-check-page',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './sync-check-page.component.html',
  styleUrl: './sync-check-page.component.scss',
})
export class SyncCheckPageComponent {
  fdFile = signal<File | null>(null);
  planFile = signal<File | null>(null);

  status = signal<Status>('idle');
  errorMessage = signal<string>('');

  // Bundle state: one entry per discipline carved out of the FD upload.
  // For a single-FD upload (or non-PDF) this contains exactly one synthetic slice.
  bundleSlices = signal<FdSliceResponse[]>([]);
  sliceRuns = signal<Map<number, SliceRun>>(new Map());
  selectedSliceIndex = signal<number | null>(null);

  // Plan-level metadata (shared across all slices).
  planRoute = signal<string | null>(null);

  // Progress counters for the bundle run.
  progressDone = signal<number>(0);
  progressTotal = signal<number>(0);

  // Convenience computed: the result for the currently selected slice.
  result = computed<CrossValidationResult | null>(() => {
    const idx = this.selectedSliceIndex();
    if (idx === null) return null;
    return this.sliceRuns().get(idx)?.result ?? null;
  });

  fdRoute = computed<string | null>(() => {
    const idx = this.selectedSliceIndex();
    if (idx === null) return null;
    return this.sliceRuns().get(idx)?.fdRoute ?? null;
  });

  /** Competency mapping (UC 2.2) for the currently selected slice. */
  competencyMapping = computed<CompetencyMapping | null>(() => {
    const idx = this.selectedSliceIndex();
    if (idx === null) return null;
    return this.sliceRuns().get(idx)?.competencyMapping ?? null;
  });

  competencyError = computed<string | null>(() => {
    const idx = this.selectedSliceIndex();
    if (idx === null) return null;
    return this.sliceRuns().get(idx)?.competencyError ?? null;
  });

  /** UC 1.2 — numeric consistency report for the currently selected slice. */
  numericReport = computed<NumericConsistencyReport | null>(() => {
    const idx = this.selectedSliceIndex();
    if (idx === null) return null;
    return this.sliceRuns().get(idx)?.numericReport ?? null;
  });

  numericError = computed<string | null>(() => {
    const idx = this.selectedSliceIndex();
    if (idx === null) return null;
    return this.sliceRuns().get(idx)?.numericError ?? null;
  });

  /** UC 3.1 — bibliography freshness report for the currently selected slice. */
  bibliographyReport = computed<BibliographyReport | null>(() => {
    const idx = this.selectedSliceIndex();
    if (idx === null) return null;
    return this.sliceRuns().get(idx)?.bibliographyReport ?? null;
  });

  bibliographyError = computed<string | null>(() => {
    const idx = this.selectedSliceIndex();
    if (idx === null) return null;
    return this.sliceRuns().get(idx)?.bibliographyError ?? null;
  });

  isBundle = computed(() => this.bundleSlices().length > 1);

  /** True when at least one slice has finished (successfully or with error). */
  canDownloadReport = computed(() => {
    for (const run of this.sliceRuns().values()) {
      if (run.status === 'done' || run.status === 'error') return true;
    }
    return false;
  });

  constructor(private sync: SyncCheckService) {}

  onFdSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.fdFile.set(input.files?.[0] ?? null);
    this.resetRunState();
  }

  onPlanSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.planFile.set(input.files?.[0] ?? null);
    this.resetRunState();
  }

  canRun(): boolean {
    const s = this.status();
    return (
      !!this.fdFile() &&
      !!this.planFile() &&
      s !== 'splitting' &&
      s !== 'parsing' &&
      s !== 'validating'
    );
  }

  async run(): Promise<void> {
    const fd = this.fdFile();
    const plan = this.planFile();
    if (!fd || !plan) return;

    this.resetRunState();
    this.errorMessage.set('');

    try {
      // Step 1: split the FD upload into slices (one per discipline).
      // Non-PDF uploads (images) skip splitting and become a single synthetic slice.
      let slices: FdSliceResponse[];
      const isPdf = /\.pdf$/i.test(fd.name) || fd.type === 'application/pdf';
      if (isPdf) {
        this.status.set('splitting');
        const split = await firstValueFrom(this.sync.splitBundle(fd));
        slices = split.slices.length > 0 ? split.slices : [];
      } else {
        slices = [];
      }

      if (slices.length === 0) {
        // Treat as a single slice using the original file.
        slices = [
          {
            index: 1,
            course_name_hint: fd.name,
            page_start: 1,
            page_end: 1,
            pdf_base64: '', // sentinel: use the original File object below
          },
        ];
      }

      this.bundleSlices.set(slices);
      const initialRuns = new Map<number, SliceRun>();
      for (const s of slices) initialRuns.set(s.index, { status: 'pending' });
      this.sliceRuns.set(initialRuns);
      this.progressTotal.set(slices.length);
      this.progressDone.set(0);
      this.selectedSliceIndex.set(slices[0].index);

      // Step 2: parse the plan once (cached on backend by sha256).
      this.status.set('parsing');
      const planDoc = await firstValueFrom(this.sync.parse(plan));
      this.planRoute.set(planDoc.source_route ?? null);

      // Step 3: validate each slice. Process with limited concurrency.
      this.status.set('validating');
      await this.runSlices(slices, fd, planDoc, 3);

      this.status.set('done');
    } catch (err: unknown) {
      const detail = this.errorDetail(err);
      console.error('[sync-check] run failed', err);
      this.errorMessage.set(detail);
      this.status.set('error');
    }
  }

  /**
   * Process all slices in parallel batches of `concurrency`. Each slice is
   * parsed (or reuses the original FD file) then cross-validated against the
   * already-parsed plan. Per-slice errors are isolated and don't abort the run.
   */
  private async runSlices(
    slices: FdSliceResponse[],
    originalFd: File,
    planDoc: ExtractedDocument,
    concurrency: number,
  ): Promise<void> {
    let cursor = 0;
    const workers: Promise<void>[] = [];
    const next = async (): Promise<void> => {
      while (true) {
        const i = cursor++;
        if (i >= slices.length) return;
        const slice = slices[i];
        await this.processSlice(slice, originalFd, planDoc);
        this.progressDone.update((n) => n + 1);
      }
    };
    for (let i = 0; i < Math.min(concurrency, slices.length); i++) {
      workers.push(next());
    }
    await Promise.all(workers);
  }

  private async processSlice(
    slice: FdSliceResponse,
    originalFd: File,
    planDoc: ExtractedDocument,
  ): Promise<void> {
    this.updateRun(slice.index, { status: 'running' });
    try {
      const fdDoc = await firstValueFrom(
        slice.pdf_base64
          ? this.sync.parseBlob(
              base64ToBlob(slice.pdf_base64),
              this.sliceFilename(slice, originalFd.name),
            )
          : this.sync.parse(originalFd),
      );

      const mismatch = this.detectSlotMismatch(fdDoc, planDoc);
      if (mismatch) {
        this.updateRun(slice.index, {
          status: 'error',
          fdRoute: fdDoc.source_route,
          error: mismatch,
        });
        return;
      }

      const res = await firstValueFrom(
        this.sync.crossValidate(fdDoc, planDoc).pipe(
          catchError((err) => {
            this.updateRun(slice.index, {
              status: 'error',
              fdRoute: fdDoc.source_route,
              error: this.errorDetail(err),
            });
            return of(null);
          }),
        ),
      );
      if (res) {
        this.updateRun(slice.index, {
          status: 'done',
          fdRoute: fdDoc.source_route,
          result: res,
        });
        // UC 2.2: best-effort competency mapping. Runs in background; failure is non-fatal.
        this.runCompetencyMapping(slice.index, fdDoc, planDoc);
        // UC 1.2 + UC 3.1: numeric consistency + bibliography freshness.
        this.runNumericConsistency(slice.index, fdDoc);
        this.runBibliography(slice.index, fdDoc);
      }
    } catch (err: unknown) {
      this.updateRun(slice.index, {
        status: 'error',
        error: this.errorDetail(err),
      });
    }
  }

  private updateRun(index: number, patch: Partial<SliceRun>): void {
    const next = new Map(this.sliceRuns());
    const prev = next.get(index) ?? { status: 'pending' };
    next.set(index, { ...prev, ...patch });
    this.sliceRuns.set(next);
  }

  private async runCompetencyMapping(
    index: number,
    fdDoc: ExtractedDocument,
    planDoc: ExtractedDocument,
  ): Promise<void> {
    try {
      const mapping = await firstValueFrom(this.sync.mapCompetencies(fdDoc, planDoc));
      this.updateRun(index, { competencyMapping: mapping });
    } catch (err: unknown) {
      this.updateRun(index, { competencyError: this.errorDetail(err) });
    }
  }

  private async runNumericConsistency(
    index: number,
    fdDoc: ExtractedDocument,
  ): Promise<void> {
    try {
      const report = await firstValueFrom(this.sync.checkNumericConsistency(fdDoc));
      this.updateRun(index, { numericReport: report });
    } catch (err: unknown) {
      this.updateRun(index, { numericError: this.errorDetail(err) });
    }
  }

  private async runBibliography(
    index: number,
    fdDoc: ExtractedDocument,
  ): Promise<void> {
    try {
      const report = await firstValueFrom(this.sync.checkFdBibliography(fdDoc));
      this.updateRun(index, { bibliographyReport: report });
    } catch (err: unknown) {
      this.updateRun(index, { bibliographyError: this.errorDetail(err) });
    }
  }

  private sliceFilename(slice: FdSliceResponse, original: string): string {
    const stem = original.replace(/\.pdf$/i, '');
    return `${stem}__slice${slice.index}.pdf`;
  }

  private errorDetail(err: unknown): string {
    const e = err as { error?: { detail?: unknown }; status?: number; statusText?: string; message?: string; name?: string };
    const backendDetail = e?.error?.detail;
    const httpStatus = e?.status;
    if (backendDetail) return String(backendDetail);
    if (e?.name === 'TimeoutError') {
      return 'Timeout: serverul nu a răspuns în limita de timp. Încearcă cu un PDF mai mic.';
    }
    if (httpStatus) return `HTTP ${httpStatus}: ${e?.statusText || e?.message || 'eroare necunoscută'}`;
    return e?.message || 'Eroare necunoscută.';
  }

  selectSlice(index: number): void {
    this.selectedSliceIndex.set(index);
  }

  reset(): void {
    this.fdFile.set(null);
    this.planFile.set(null);
    this.errorMessage.set('');
    this.resetRunState();
  }

  private resetRunState(): void {
    this.bundleSlices.set([]);
    this.sliceRuns.set(new Map());
    this.selectedSliceIndex.set(null);
    this.planRoute.set(null);
    this.progressDone.set(0);
    this.progressTotal.set(0);
    this.status.set('idle');
  }

  // ----- View helpers -------------------------------------------------------

  /** Status badge for the currently selected slice's result. */
  statusBadge(): { label: string; className: string } {
    const r = this.result();
    if (!r) return { label: '—', className: 'badge-neutral' };
    return this.statusBadgeFor(r.status);
  }

  /** Status badge for any cross-validation status (used in the coverage table). */
  statusBadgeFor(status: CrossValidationResult['status'] | undefined | null): { label: string; className: string } {
    switch (status) {
      case 'valid':
        return { label: 'Aliniat', className: 'badge-valid' };
      case 'invalid':
        return { label: 'Inconsistent', className: 'badge-invalid' };
      case 'no_match':
        return { label: 'Nepotrivit', className: 'badge-warning' };
      default:
        return { label: '—', className: 'badge-neutral' };
    }
  }

  /** Row badge for a slice based on its run state (pending/running/error/done). */
  sliceRowBadge(index: number): { label: string; className: string } {
    const run = this.sliceRuns().get(index);
    if (!run) return { label: 'În așteptare', className: 'badge-neutral' };
    switch (run.status) {
      case 'pending':
        return { label: 'În așteptare', className: 'badge-neutral' };
      case 'running':
        return { label: 'Procesare…', className: 'badge-warning' };
      case 'error':
        return { label: 'Eroare', className: 'badge-invalid' };
      case 'done':
        return this.statusBadgeFor(run.result?.status);
    }
  }

  /** Total violation count for a slice (for the coverage table). */
  violationCount(index: number): number {
    const r = this.sliceRuns().get(index)?.result;
    if (!r) return 0;
    return r.field_violations.length + r.competency_violations.length;
  }

  /** Course name to display in the coverage row (prefer parsed FD name, fall back to splitter hint). */
  rowCourseName(slice: FdSliceResponse): string {
    const parsed = this.sliceRuns().get(slice.index)?.result?.fd_course_name;
    return parsed || slice.course_name_hint || `Disciplina #${slice.index}`;
  }

  selectedRunError(): string | null {
    const idx = this.selectedSliceIndex();
    if (idx === null) return null;
    return this.sliceRuns().get(idx)?.error ?? null;
  }

  routeLabel(route: string | null): string {
    switch (route) {
      case 'fast_pdfplumber':
        return '⚡ Fast (pdfplumber)';
      case 'text_pdf':
        return '🤖 Claude (text)';
      case 'scanned_pdf':
      case 'image':
        return '🤖 Claude Vision';
      default:
        return route ?? '—';
    }
  }

  // ----- Report export ------------------------------------------------------

  /** Build a plain-text report covering every slice in the current bundle. */
  buildReport(): string {
    const slices = this.bundleSlices();
    const planRoute = this.routeLabel(this.planRoute());
    const fdName = this.fdFile()?.name ?? '—';
    const planName = this.planFile()?.name ?? '—';

    const totals = { aligned: 0, inconsistent: 0, no_match: 0, error: 0, pending: 0 };
    for (const s of slices) {
      const run = this.sliceRuns().get(s.index);
      if (!run) { totals.pending++; continue; }
      if (run.status === 'error') { totals.error++; continue; }
      if (run.status !== 'done') { totals.pending++; continue; }
      const st = run.result?.status;
      if (st === 'valid') totals.aligned++;
      else if (st === 'invalid') totals.inconsistent++;
      else if (st === 'no_match') totals.no_match++;
    }

    const lines: string[] = [];
    lines.push('Raport Sync-Check FD ↔ Plan de Învățământ');
    lines.push('='.repeat(60));
    lines.push(`Generat:        ${new Date().toLocaleString('ro-RO')}`);
    lines.push(`FD upload:      ${fdName}`);
    lines.push(`Plan upload:    ${planName}`);
    lines.push(`Plan parser:    ${planRoute}`);
    lines.push('');
    lines.push(`Total discipline: ${slices.length}`);
    lines.push(
      `  Aliniate: ${totals.aligned}` +
      `  ·  Inconsistente: ${totals.inconsistent}` +
      `  ·  Nepotrivite: ${totals.no_match}` +
      `  ·  Erori: ${totals.error}` +
      (totals.pending ? `  ·  În așteptare: ${totals.pending}` : ''),
    );
    lines.push('');

    for (const slice of slices) {
      lines.push('-'.repeat(60));
      const run = this.sliceRuns().get(slice.index);
      const header = `#${slice.index}  (pag. ${slice.page_start}–${slice.page_end})`;
      lines.push(header);

      if (!run || run.status === 'pending') {
        lines.push('  [În așteptare]');
        lines.push('');
        continue;
      }
      if (run.status === 'running') {
        lines.push('  [Procesare în curs]');
        lines.push('');
        continue;
      }
      if (run.status === 'error') {
        lines.push(`  [Eroare] ${run.error ?? 'necunoscută'}`);
        lines.push('');
        continue;
      }

      const r = run.result;
      if (!r) { lines.push('  [Fără rezultat]'); lines.push(''); continue; }

      const badge = this.statusBadgeFor(r.status).label;
      lines.push(badge);
      lines.push(r.fd_course_name || slice.course_name_hint || `Disciplina #${slice.index}`);
      lines.push(`FD: ${this.routeLabel(run.fdRoute ?? null)}  ·  Plan: ${planRoute}`);
      lines.push('');
      if (r.summary) {
        lines.push(r.summary.trim());
        lines.push('');
      }

      if (r.plan_match) {
        const m = r.plan_match;
        lines.push('Potrivire în Plan');
        lines.push(`  Denumire în plan : ${m.course_name}`);
        if (m.course_code) lines.push(`  Cod disciplină    : ${m.course_code}`);
        if (m.year != null) lines.push(`  An / Semestru     : ${m.year} / ${m.semester ?? '—'}`);
        if (m.credits != null) lines.push(`  Credite (Plan)    : ${m.credits}`);
        if (m.evaluation_form) lines.push(`  Evaluare (Plan)   : ${m.evaluation_form}`);
        lines.push(`  Tip potrivire     : ${m.match_confidence}`);
        lines.push('');
      }

      if (r.field_violations.length > 0) {
        lines.push('⚠ Inconsistențe administrative');
        for (const v of r.field_violations) {
          lines.push(`  - [${v.code}] ${v.message}`);
        }
        lines.push('');
      }

      if (r.competency_violations.length > 0) {
        lines.push('⚠ Competențe nealiniate');
        for (const v of r.competency_violations) {
          const codes = v.fields && v.fields.length ? ` (${v.fields.join(', ')})` : '';
          lines.push(`  - [${v.code}] ${v.message}${codes}`);
        }
        lines.push('');
      }

      if (
        r.field_violations.length === 0 &&
        r.competency_violations.length === 0 &&
        r.status === 'valid'
      ) {
        lines.push('✅ Toate verificările au trecut. FD este aliniată cu Planul de Învățământ.');
        lines.push('');
      }

      // UC 1.2 — numeric consistency report.
      if (run.numericReport) {
        const nr = run.numericReport;
        lines.push('🔢 Consistență numerică (UC 1.2)');
        lines.push(`  ${nr.summary}`);
        for (const issue of nr.issues) {
          const icon = issue.severity === 'error' ? '⛔' : issue.severity === 'warning' ? '⚠️' : 'ℹ️';
          lines.push(`  ${icon} [${issue.code}] ${issue.message}`);
        }
        lines.push('');
      } else if (run.numericError) {
        lines.push('🔢 Consistență numerică (UC 1.2)');
        lines.push(`  [Eroare] ${run.numericError}`);
        lines.push('');
      }

      // UC 3.1 — bibliography freshness report.
      if (run.bibliographyReport) {
        const br = run.bibliographyReport;
        lines.push('📚 Bibliografie (UC 3.1)');
        lines.push(`  ${br.summary}`);
        for (const e of br.entries) {
          const yearLabel = e.latest_year !== null
            ? (e.age_years !== null ? `${e.latest_year} (${e.age_years} ani)` : `${e.latest_year}`)
            : 'fără an';
          const flag = e.issues.length > 0 ? '⚠️' : '✓';
          const text = e.text.length > 120 ? e.text.slice(0, 117) + '…' : e.text;
          lines.push(`  ${flag} [${yearLabel}] ${text}`);
        }
        lines.push('');
      } else if (run.bibliographyError) {
        lines.push('📚 Bibliografie (UC 3.1)');
        lines.push(`  [Eroare] ${run.bibliographyError}`);
        lines.push('');
      }
    }

    lines.push('-'.repeat(60));
    lines.push('Sfârșitul raportului.');
    return lines.join('\n');
  }

  downloadReport(): void {
    const text = this.buildReport();
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    const stamp = new Date().toISOString().replace(/[:.]/g, '-');
    const stem = (this.fdFile()?.name ?? 'fd').replace(/\.pdf$/i, '');
    a.href = url;
    a.download = `sync-check-${stem}-${stamp}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  /**
   * Reject obvious slot mismatches before invoking cross-validate so the
   * user sees a clear "wrong upload" message instead of a downstream
   * "missing field" violation.
   */
  private detectSlotMismatch(
    fdDoc: ExtractedDocument,
    planDoc: ExtractedDocument
  ): string | null {
    const fdType = (fdDoc?.document_type || '').toLowerCase();
    const planType = (planDoc?.document_type || '').toLowerCase();

    if (fdType === 'plan_de_invatamant') {
      return 'Slotul „Fișa Disciplinei” conține un Plan de Învățământ. Încarcă o Fișă a Disciplinei (FD) acolo.';
    }
    if (planType === 'fisa_disciplinei') {
      return 'Slotul „Plan de Învățământ” conține o Fișă a Disciplinei. Încarcă un Plan de Învățământ (PI) acolo.';
    }
    if (fdType === planType && fdType) {
      return `Ai încărcat două documente de același tip (${fdType}). Trebuie o FD într-un slot și un PI în celălalt.`;
    }
    return null;
  }
}
