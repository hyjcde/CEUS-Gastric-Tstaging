/** 突破方向标注工具（direction_annotator）默认 Web 端口 */
const DEFAULT_ANNOTATOR_URL = 'http://localhost:3099';

/**
 * 标注系统 Web 入口。可通过 NEXT_PUBLIC_DIRECTION_ANNOTATOR_URL 覆盖。
 */
export function getDirectionAnnotatorUrl(): string {
  const configured = process.env.NEXT_PUBLIC_DIRECTION_ANNOTATOR_URL?.trim();
  if (configured) {
    return configured.replace(/\/$/, '');
  }
  return DEFAULT_ANNOTATOR_URL;
}
