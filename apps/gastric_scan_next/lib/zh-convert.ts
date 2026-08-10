/**
 * Simplified Chinese → Hong Kong Traditional converter (OpenCC s2hk).
 * Source of truth for Chinese UI copy remains Simplified; zh-HK is derived.
 */

import * as OpenCC from 'opencc-js';

type ConverterFn = (text: string) => string;

let converter: ConverterFn | null = null;

function getConverter(): ConverterFn {
  if (!converter) {
    converter = OpenCC.Converter({ from: 'cn', to: 'hk' });
  }
  return converter;
}

const HAS_CJK = /[\u4e00-\u9fff]/;

/** Convert Simplified → Hong Kong Traditional. Non-Chinese text is returned unchanged. */
export function toTraditionalHK(text: string): string {
  if (!text || !HAS_CJK.test(text)) return text;
  try {
    return getConverter()(text);
  } catch {
    return text;
  }
}

/** Deep-convert string leaves of a plain object / array tree. */
export function deepToTraditionalHK<T>(value: T): T {
  if (typeof value === 'string') {
    return toTraditionalHK(value) as T;
  }
  if (Array.isArray(value)) {
    return value.map((item) => deepToTraditionalHK(item)) as T;
  }
  if (value && typeof value === 'object') {
    const out: Record<string, unknown> = {};
    for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
      out[key] = deepToTraditionalHK(child);
    }
    return out as T;
  }
  return value;
}

const SKIP_TAGS = new Set([
  'SCRIPT',
  'STYLE',
  'TEXTAREA',
  'INPUT',
  'SELECT',
  'OPTION',
  'CODE',
  'PRE',
  'KBD',
  'SAMP',
]);

function shouldSkipNode(node: Node): boolean {
  let current: Node | null = node;
  while (current) {
    if (current.nodeType === Node.ELEMENT_NODE) {
      const el = current as Element;
      if (SKIP_TAGS.has(el.tagName)) return true;
      if (el.getAttribute('data-no-zh-convert') != null) return true;
      if (el.getAttribute('contenteditable') === 'true') return true;
    }
    current = current.parentNode;
  }
  return false;
}

/** Convert Simplified text nodes under root when locale is zh-HK. */
export function convertDomToTraditionalHK(root: ParentNode = document.body): number {
  if (typeof document === 'undefined') return 0;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let changed = 0;
  let node = walker.nextNode();
  while (node) {
    const textNode = node as Text;
    const raw = textNode.nodeValue || '';
    if (raw && HAS_CJK.test(raw) && !shouldSkipNode(textNode)) {
      const next = toTraditionalHK(raw);
      if (next !== raw) {
        textNode.nodeValue = next;
        changed += 1;
      }
    }
    node = walker.nextNode();
  }
  return changed;
}
