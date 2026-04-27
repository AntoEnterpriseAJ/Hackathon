import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, timeout } from 'rxjs';

import {
  ExtractedDocument,
  FdDraft,
  PlanCourseListResponse,
} from '../models/draft.models';

@Injectable({ providedIn: 'root' })
export class DraftService {
  private apiUrl = '/api/documents';
  private parseTimeoutMs = 600000; // 10 min — Claude OCR is slow
  private quickTimeoutMs = 60000;
  private aiTimeoutMs = 600000;

  constructor(private http: HttpClient) {}

  parsePlan(file: File): Observable<ExtractedDocument> {
    const formData = new FormData();
    formData.append('file', file, file.name);
    return this.http
      .post<ExtractedDocument>(`${this.apiUrl}/parse`, formData)
      .pipe(timeout(this.parseTimeoutMs));
  }

  listCourses(plan: ExtractedDocument): Observable<PlanCourseListResponse> {
    return this.http
      .post<PlanCourseListResponse>(`${this.apiUrl}/list-plan-courses`, { plan })
      .pipe(timeout(this.quickTimeoutMs));
  }

  draft(
    plan: ExtractedDocument,
    courseName: string,
    courseCode: string | null,
    useClaude: boolean,
  ): Observable<FdDraft> {
    return this.http
      .post<FdDraft>(`${this.apiUrl}/draft-fd`, {
        plan,
        course_name: courseName,
        course_code: courseCode,
        use_claude: useClaude,
      })
      .pipe(timeout(this.aiTimeoutMs));
  }

  draftDocx(
    plan: ExtractedDocument,
    courseName: string,
    courseCode: string | null,
    useClaude: boolean,
  ): Observable<Blob> {
    return this.http
      .post(
        `${this.apiUrl}/draft-fd-docx`,
        {
          plan,
          course_name: courseName,
          course_code: courseCode,
          use_claude: useClaude,
        },
        { responseType: 'blob' },
      )
      .pipe(timeout(this.aiTimeoutMs));
  }
}
