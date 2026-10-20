// ============================================================
// JobPilot AI — API Client (Fetch Wrapper for FastAPI Backend)
// ============================================================

import { API_URL } from './constants';

interface RequestOptions extends Omit<RequestInit, 'body'> {
  body?: unknown;
}

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  private async getAuthToken(): Promise<string | null> {
    const { supabase } = await import('./supabase');
    const { data: { session } } = await supabase.auth.getSession();
    return session?.access_token ?? null;
  }


  private async request<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
    const { body, headers: customHeaders, ...rest } = options;

    const token = await this.getAuthToken();

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...((customHeaders as Record<string, string>) || {}),
    };

    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const config: RequestInit = {
      ...rest,
      headers,
    };

    if (body) {
      config.body = JSON.stringify(body);
    }

    const response = await fetch(`${this.baseUrl}${endpoint}`, config);

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
    const token = await this.getAuthToken();
    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!response.ok) {
      throw await this.toError(response);
    }
    return response.blob();
  }

  /** POST a file as multipart form data (the browser sets the boundary header). */
  async upload<T>(endpoint: string, file: File, field = 'file'): Promise<T> {
    const token = await this.getAuthToken();
    const form = new FormData();
    form.append(field, file);
    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: form,
    });
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
