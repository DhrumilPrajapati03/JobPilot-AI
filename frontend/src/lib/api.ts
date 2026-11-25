// ============================================================
// JobDots — API Client (Fetch Wrapper for FastAPI Backend)
// ============================================================

import { API_URL } from './constants';
import { accountContext } from './account-context';
import { sessionInit } from './session';

interface RequestOptions extends Omit<RequestInit, 'body'> {
  body?: unknown;
  expectedUserId?: string;
}

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  /** Requests stay with the account they began in (the cookie may change underneath). */
  private checkAccount(started: ReturnType<typeof accountContext>, expectedUserId?: string) {
    const now = accountContext();
    if ((expectedUserId && now.account !== expectedUserId) || now.revision !== started.revision) {
      throw new Error('Account changed. Reopen this page before continuing.');
    }
  }

  private async request<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
    const { body, expectedUserId, headers: customHeaders, ...rest } = options;

    const started = accountContext();
    this.checkAccount(started, expectedUserId);

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...((customHeaders as Record<string, string>) || {}),
    };

    const config: RequestInit = sessionInit({
      ...rest,
      headers,
    });

    if (body) {
      config.body = JSON.stringify(body);
    }

    const response = await fetch(`${this.baseUrl}${endpoint}`, config);
    // A reply that lands after an account switch belongs to the old account: drop it.
    this.checkAccount(started, expectedUserId);

    if (!response.ok) {
      throw await this.toError(response);
    }

    // Handle 204 No Content
    if (response.status === 204) {
      return undefined as T;
    }

    return response.json();
  }

  private async toError(response: Response): Promise<Error> {
    const error = await response.json().catch(() => ({}));
    // FastAPI returns { detail: string } or, for validation errors, { detail: [{ msg }] }
    const detail = Array.isArray(error.detail)
      ? error.detail.map((d: { msg?: string }) => d.msg).join('; ')
      : error.detail;
    return new Error(detail || error.message || `Request failed with status ${response.status}`);
  }

  /** Fetch a binary response (e.g. a generated PDF) with auth. */
  async getBlob(endpoint: string): Promise<Blob> {
    this.checkAccount(accountContext());
    const response = await fetch(`${this.baseUrl}${endpoint}`, sessionInit());
    if (!response.ok) {
      throw await this.toError(response);
    }
    return response.blob();
  }

  /** POST a file as multipart form data (the browser sets the boundary header). */
  async upload<T>(endpoint: string, file: File, field = 'file', expectedUserId?: string): Promise<T> {
    this.checkAccount(accountContext(), expectedUserId);
    const form = new FormData();
    form.append(field, file);
    const response = await fetch(`${this.baseUrl}${endpoint}`, sessionInit({ method: 'POST', body: form }));
    if (!response.ok) {
      throw await this.toError(response);
    }
    return response.json();
  }

  async get<T>(endpoint: string, options?: RequestOptions): Promise<T> {
    return this.request<T>(endpoint, { ...options, method: 'GET' });
  }

  async post<T>(endpoint: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return this.request<T>(endpoint, { ...options, method: 'POST', body });
  }

  async put<T>(endpoint: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return this.request<T>(endpoint, { ...options, method: 'PUT', body });
  }

  async patch<T>(endpoint: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return this.request<T>(endpoint, { ...options, method: 'PATCH', body });
  }

  async delete<T>(endpoint: string, options?: RequestOptions): Promise<T> {
    return this.request<T>(endpoint, { ...options, method: 'DELETE' });
  }
}

export const api = new ApiClient(API_URL);
export default api;
