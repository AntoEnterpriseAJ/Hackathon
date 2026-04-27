/**
 * DiffService - HTTP adapter for diff API.
 * Thin layer between components and backend.
 */

import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, timeout } from 'rxjs';
import { DiffResponse, DiffNarrative } from '../models/diff.models';

@Injectable({
  providedIn: 'root'
})
export class DiffService {
  private apiUrl = 'http://localhost:8001/api/documents';
  private compareTimeoutMs = 300000;

  constructor(private http: HttpClient) { }

  /**
   * Compare two PDF documents.
   * @param fileOld First PDF file
   * @param fileNew Second PDF file
   * @param parserType Optional: 'fd' or 'pi' (default: 'fd')
   */
  compare(
    fileOld: File,
    fileNew: File,
    parserType: 'fd' | 'pi' = 'fd'
  ): Observable<DiffResponse> {
    const formData = new FormData();
    formData.append('file_old', fileOld);
    formData.append('file_new', fileNew);
    formData.append('parser_type', parserType);

    return this.http
      .post<DiffResponse>(`${this.apiUrl}/diff`, formData)
      .pipe(timeout(this.compareTimeoutMs));
  }

  /**
   * Check health of the diff service.
   */
  health(): Observable<{ status: string }> {
    // The backend might not have a /health endpoint, returning dummy data for now
    return new Observable(obs => obs.next({ status: 'ok' }));
  }

  /**
   * POST /api/documents/explain-diff (FastAPI, via proxy) — turn a DiffResponse into a
   * human-language narrative + key changes + action items.
   */
  explainDiff(diff: DiffResponse): Observable<DiffNarrative> {
    return this.http
      .post<DiffNarrative>('/api/documents/explain-diff', { diff })
      .pipe(timeout(this.compareTimeoutMs));
  }

  /**
   * Visually compare two PDF documents.
   */
  visualCompare(fileOld: File, fileNew: File): Observable<{ annotated_old_pdf_base64: string; annotated_new_pdf_base64: string }> {
    const formData = new FormData();
    formData.append('file_old', fileOld);
    formData.append('file_new', fileNew);

    return this.http.post<{ annotated_old_pdf_base64: string; annotated_new_pdf_base64: string }>(`${this.apiUrl}/diff-visual`, formData);
  }
}
