export const DOCTOR_SESSION_STORAGE_KEY = 'gastric_doctor_session_token';
export const DOCTOR_SESSION_HEADER = 'x-doctor-session-token';

export function getDoctorSessionToken(): string {
  if (typeof window === 'undefined') return '';
  try {
    return String(window.localStorage.getItem(DOCTOR_SESSION_STORAGE_KEY) || '').trim();
  } catch {
    return '';
  }
}

export function setDoctorSessionToken(token: string | null) {
  if (typeof window === 'undefined') return;
  try {
    if (!token) {
      window.localStorage.removeItem(DOCTOR_SESSION_STORAGE_KEY);
      return;
    }
    window.localStorage.setItem(DOCTOR_SESSION_STORAGE_KEY, token);
  } catch {
    // Ignore storage failures; session simply will not persist.
  }
}

export function doctorAuthHeaders(extra: HeadersInit = {}): HeadersInit {
  const token = getDoctorSessionToken();
  const headers = new Headers(extra);
  if (token) {
    headers.set(DOCTOR_SESSION_HEADER, token);
    if (!headers.has('Authorization')) {
      headers.set('Authorization', `Bearer ${token}`);
    }
  }
  return headers;
}
