const DEFAULT_VIDEO_ANNOTATOR_URL = 'http://127.0.0.1:3100';

/** 视频/多模态标注平台（MedDINO gastric-annotator）默认 Web 端口 */
export function getVideoAnnotatorUrl(): string {
  const configured = process.env.NEXT_PUBLIC_VIDEO_ANNOTATOR_URL?.trim();
  if (configured) {
    return configured.replace(/\/$/, '');
  }
  return DEFAULT_VIDEO_ANNOTATOR_URL;
}

export function getVideoAnnotatorRoot(): string {
  return process.env.VIDEO_ANNOTATOR_ROOT?.trim()
    || '/data/research/gastric/Tstaging/archived/legacy_tools_v1/annotators/video_annotator';
}
