import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, timeout } from 'rxjs';

import {
  BibliographyReport,
  CompetencyMapping,
  CrossValidationResult,
  ExtractedDocument,
  NumericConsistencyReport,
  SplitFdBundleResponse,
  StructuralValidationResult,
} from '../models/sync.models';

@Injectable({ providedIn: 'root' })
export class SyncCheckService {
  private apiUrl = '/api/documents';
  private parseTimeoutMs = 600000; // 10 minutes — Claude OCR on multi-page PDFs is slow
  private validateTimeoutMs = 60000;
  private splitTimeoutMs = 120000;

  constructor(private http: HttpClient) {}

  /** POST /api/documents/parse — multipart upload of a single file. */
  parse(file: File): Observable<ExtractedDocument> {
    return this.parseBlob(file, file.name);
  }

  /** POST /api/documents/parse with an arbitrary Blob (used for bundle slices). */
  parseBlob(blob: Blob, filename: string): Observable<ExtractedDocument> {
    const formData = new FormData();
    formData.append('file', blob, filename);
    return this.http
      .post<ExtractedDocument>(`${this.apiUrl}/parse`, formData)
      .pipe(timeout(this.parseTimeoutMs));
  }

  /** POST /api/documents/cross-validate — JSON body with already-parsed FD + Plan. */
  crossValidate(fd: ExtractedDocument, plan: ExtractedDocument): Observable<CrossValidationResult> {
    return this.http
      .post<CrossValidationResult>(`${this.apiUrl}/cross-validate`, { fd, plan })
      .pipe(timeout(this.validateTimeoutMs));
  }

  /** POST /api/documents/split-fd-bundle — carve a multi-FD PDF into per-discipline slices. */
  splitBundle(file: File): Observable<SplitFdBundleResponse> {
    const formData = new FormData();
    formData.append('file', file);
    return this.http
      .post<SplitFdBundleResponse>(`${this.apiUrl}/split-fd-bundle`, formData)
      .pipe(timeout(this.splitTimeoutMs));
  }

  /** POST /api/documents/map-competencies — UC 2.2 mapping (deterministic + optional AI). */
  mapCompetencies(
    fd: ExtractedDocument,
    plan: ExtractedDocument,
    useClaude: boolean | null = null,
  ): Observable<CompetencyMapping> {
    return this.http
      .post<CompetencyMapping>(`${this.apiUrl}/map-competencies`, {
        fd,
        plan,
        use_claude: useClaude,
      })
      .pipe(timeout(this.parseTimeoutMs));
  }

  /** POST /api/documents/check-numeric-consistency — UC 1.2 internal arithmetic checks. */
  checkNumericConsistency(fd: ExtractedDocument): Observable<NumericConsistencyReport> {
    return this.http
      .post<NumericConsistencyReport>(`${this.apiUrl}/check-numeric-consistency`, { fd })
      .pipe(timeout(this.validateTimeoutMs));
  }

  /** POST /api/documents/check-fd-bibliography — UC 3.1 bibliography freshness. */
  checkFdBibliography(
    fd: ExtractedDocument,
    options: { maxAgeYears?: number; checkUrls?: boolean } = {},
  ): Observable<BibliographyReport> {
    return this.http
      .post<BibliographyReport>(`${this.apiUrl}/check-fd-bibliography`, {
        fd,
        max_age_years: options.maxAgeYears ?? 5,
        check_urls: options.checkUrls ?? false,
      })
      .pipe(timeout(this.validateTimeoutMs));
  }

  /**
   * POST /api/documents/validate — UC 1.1 structural field-presence check.
   * Converts the flat ExtractedDocument fields array into a dict and validates
   * against a hardcoded FD schema with required-field + guard rules.
   */
  validateStructure(fd: ExtractedDocument): Observable<StructuralValidationResult> {
    const template: Record<string, unknown> = {};
    for (const f of fd.fields) {
      template[f.key] = f.value;
    }

    const schema = {
      fields: {
        denumirea_disciplinei:                                { required: true,  type: 'string' },
        titularul_activitatilor_de_curs:                     { required: true,  type: 'string' },
        titularul_activitatilor_de_seminar_laborator_proiect: { required: true,  type: 'string' },
        obiective_generale_ale_disciplinei:                  { required: true,  type: 'string' },
        competente_profesionale:                             { required: true,  type: 'list'   },
        competente_transversale:                             { required: true,  type: 'list'   },
        bibliografie:                                        { required: false, type: 'list'   },
        semestrul:                                           { required: true,  type: 'number' },
        anul_de_studiu:                                      { required: true,  type: 'number' },
        numarul_de_credite:                                  { required: true,  type: 'number' },
        tipul_de_evaluare:                                   { required: true,  type: 'string' },
      },
    };

    const guards = [
      {
        code: 'credits_range',
        kind: 'range',
        field: 'numarul_de_credite',
        min_value: 1,
        max_value: 30,
        message: 'Credit count must be between 1 and 30.',
      },
    ];

    return this.http
      .post<StructuralValidationResult>(`${this.apiUrl}/validate`, {
        template,
        schema,
        guards,
      })
      .pipe(timeout(this.validateTimeoutMs));
  }
}
