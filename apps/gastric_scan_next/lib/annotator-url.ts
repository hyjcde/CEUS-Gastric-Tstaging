/** 标注工具路由（已合并进主应用） */
export function getDirectionAnnotatorPath(): string {
  return '/annotate';
}

/** @deprecated 保留兼容；合并后默认走主应用内 /annotate */
export function getDirectionAnnotatorUrl(): string {
  const configured = process.env.NEXT_PUBLIC_DIRECTION_ANNOTATOR_URL?.trim();
  if (configured) {
    return configured.replace(/\/$/, '');
  }
  return getDirectionAnnotatorPath();
}
