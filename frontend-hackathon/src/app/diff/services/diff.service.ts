/**
 * DiffService - HTTP adapter for diff API.
 * Thin layer between components and backend.
 */

import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { DiffResponse } from '../models/diff.models';

@Injectable({
  providedIn: 'root'
})
export class DiffService {
  private apiUrl = 'http://localhost:5000/api/diff';

  constructor(private http: HttpClient) {}

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

    return this.http.post<DiffResponse>(`${this.apiUrl}/`, formData);
  }

  /**
   * Check health of the diff service.
   */
  health(): Observable<{ status: string }> {
    return this.http.get<{ status: string }>(`${this.apiUrl}/health`);
  }
}
