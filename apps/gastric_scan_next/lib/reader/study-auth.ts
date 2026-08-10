import crypto from 'node:crypto';

const DEFAULT_READER_ID_HEADER = 'x-authenticated-reader-id';
const DEFAULT_READER_SIGNATURE_HEADER = 'x-authenticated-reader-signature';

export type ReaderAuthResult =
  | { ok: true; readerId: string; authMode: 'signed_proxy' | 'unsigned_development' }
  | { ok: false; code: 'missing_identity' | 'missing_secret' | 'missing_signature' | 'invalid_signature' | 'invalid_identity'; message: string };

function configuredHeader(name: string, fallback: string): string {
  return process.env[name]?.trim() || fallback;
}

export function normalizeReaderId(value: unknown): string {
  const normalized = String(value ?? '').trim();
  return /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(normalized) ? normalized : '';
}

function safeEqualHex(left: string, right: string): boolean {
  if (!/^[a-f0-9]{64}$/i.test(left) || !/^[a-f0-9]{64}$/i.test(right)) return false;
  return crypto.timingSafeEqual(Buffer.from(left, 'hex'), Buffer.from(right, 'hex'));
}

/**
 * Research identity is supplied by the authenticated reverse proxy.
 *
 * The proxy must inject the reader ID and an HMAC-SHA256 signature over that
 * ID. Direct browser-provided reader_id values are never accepted for research.
 */
export function resolveAuthenticatedReader(headers: Headers): ReaderAuthResult {
  const idHeader = configuredHeader('READER_AUTH_ID_HEADER', DEFAULT_READER_ID_HEADER);
  const signatureHeader = configuredHeader('READER_AUTH_SIGNATURE_HEADER', DEFAULT_READER_SIGNATURE_HEADER);
  const readerId = normalizeReaderId(headers.get(idHeader));
  if (!readerId) {
    return {
      ok: false,
      code: 'missing_identity',
      message: `Missing authenticated reader identity in ${idHeader}`,
    };
  }

  const secret = process.env.READER_AUTH_PROXY_SECRET?.trim();
  if (!secret) {
    if (process.env.NODE_ENV !== 'production' && process.env.READER_ALLOW_UNSIGNED_RESEARCH_AUTH === '1') {
      return { ok: true, readerId, authMode: 'unsigned_development' };
    }
    return {
      ok: false,
      code: 'missing_secret',
      message: 'READER_AUTH_PROXY_SECRET is not configured',
    };
  }

  const signature = String(headers.get(signatureHeader) || '')
    .trim()
    .replace(/^sha256=/i, '');
  if (!signature) {
    return {
      ok: false,
      code: 'missing_signature',
      message: `Missing authenticated reader signature in ${signatureHeader}`,
    };
  }
  const expected = crypto.createHmac('sha256', secret).update(readerId, 'utf8').digest('hex');
  if (!safeEqualHex(signature, expected)) {
    return {
      ok: false,
      code: 'invalid_signature',
      message: 'Authenticated reader signature is invalid',
    };
  }
  return { ok: true, readerId, authMode: 'signed_proxy' };
}

export function resolveResearchReader(
  headers: Headers,
  requestedReaderId?: unknown,
): ReaderAuthResult {
  const result = resolveAuthenticatedReader(headers);
  if (!result.ok) return result;
  const requested = normalizeReaderId(requestedReaderId);
  if (requested && requested !== result.readerId) {
    return {
      ok: false,
      code: 'invalid_identity',
      message: 'URL or body reader_id does not match authenticated reader identity',
    };
  }
  return result;
}
