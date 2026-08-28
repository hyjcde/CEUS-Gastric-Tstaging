/** Educational copy for the wall-layer dock. Draft echo reading only; never unlocks cT. */

export type WallLayerCode = 'L1' | 'L2' | 'L3' | 'L4' | 'L5';

export type WallLayerGuide = {
  code: WallLayerCode;
  frac0: number;
  frac1: number;
  color: string;
  zh: string;
  en: string;
  shortZh: string;
  shortEn: string;
  echoZh: string;
  echoEn: string;
  lookZh: string;
  lookEn: string;
  stagingZh: string;
  stagingEn: string;
};

export const WALL_LAYER_GUIDES: WallLayerGuide[] = [
  {
    code: 'L1',
    frac0: 0,
    frac1: 0.2,
    color: '#38bdf8',
    zh: '黏膜层',
    en: 'Mucosa',
    shortZh: '黏膜',
    shortEn: 'Mucosa',
    echoZh: '最靠近胃腔的一层。充盈超声里常是第一条亮或暗界面。',
    echoEn: 'Innermost band, next to the lumen. Often the first bright or dark interface on filled gastric US.',
    lookZh: '看黏膜面是否被病灶顶起，这一层是否还能成层。',
    lookEn: 'See whether the mucosal face is lifted and whether this band still reads as a layer.',
    stagingZh: '阅片时多当作浅层参考（T1a 一带）。这是回声草稿，不是病理层，也不定 cT。',
    stagingEn: 'Usually read as a shallow reference (around T1a). Echo draft only, not a pathologic layer, and not a definite cT.',
  },
  {
    code: 'L2',
    frac0: 0.2,
    frac1: 0.4,
    color: '#a78bfa',
    zh: '黏膜肌层',
    en: 'Muscularis mucosae',
    shortZh: '黏膜肌',
    shortEn: 'MM',
    echoZh: '很薄，常是第二条暗带。本帧经常和黏膜合在一起，分不清是正常的。',
    echoEn: 'A thin second dark band. It often merges with mucosa on a single frame; that is common.',
    lookZh: '不要为了凑满五层去硬分。看不清就写看不清。',
    lookEn: 'Do not force a fifth-layer split. Mark it unseen when the band is not there.',
    stagingZh: '仍属浅层参考。单独这一层看不清，不能当成已经进入更深。不定 cT。',
    stagingEn: 'Still a shallow reference. A missing MM band is not deeper invasion. Not a definite cT.',
  },
  {
    code: 'L3',
    frac0: 0.4,
    frac1: 0.6,
    color: '#2dd4bf',
    zh: '黏膜下层',
    en: 'Submucosa',
    shortZh: '黏膜下',
    shortEn: 'SM',
    echoZh: '多在走廊中段，常是一条较亮的带。',
    echoEn: 'Usually a brighter mid-corridor band.',
    lookZh: '看这条亮带有没有被低回声灶换掉，还是还能顺着走。',
    lookEn: 'See whether the bright band is replaced by hypoechoic tumor or still tracks along the wall.',
    stagingZh: '阅片时 T1b 会进这一层；穿过它再谈固有肌。仍是草稿，不定 cT。',
    stagingEn: 'T1b is often discussed here; crossing it raises the MP question. Still a draft, not a definite cT.',
  },
  {
    code: 'L4',
    frac0: 0.6,
    frac1: 0.8,
    color: '#4ade80',
    zh: '固有肌层',
    en: 'Muscularis propria',
    shortZh: '固有肌',
    shortEn: 'MP',
    echoZh: '通常是较厚的低回声带，在浆膜亮线内侧。',
    echoEn: 'Usually a thicker hypoechoic band inside the serosal bright line.',
    lookZh: '看固有肌外缘是否还在。外侧若还有亮线，更像还没到浆膜。',
    lookEn: 'Check the MP outer edge. A bright line outside it still looks more like serosa not reached.',
    stagingZh: 'T2 / T3 纠结时主看这一层外缘。几何外推只是参考，不定 cT。',
    stagingEn: 'T2 vs T3 is usually this outer edge. Geometric offset is only a guide. Not a definite cT.',
  },
  {
    code: 'L5',
    frac0: 0.8,
    frac1: 1,
    color: '#fb7185',
    zh: '浆膜 / 浆膜下',
    en: 'Serosa / subserosa',
    shortZh: '浆膜',
    shortEn: 'Serosa',
    echoZh: '最外一条高回声亮线。剖面图黄线是亮峰，虚线是几何外缘。',
    echoEn: 'Outermost hyperechoic line. Gold on the profile is the bright peak; the dashed line is the geometric outer edge.',
    lookZh: '先看有没有贴到这条亮线，再看亮线还在、中断，还是看不清。看不清不要当成中断。',
    lookEn: 'First ask if the front reached this line, then whether it stays, breaks, or is unseen. Unseen is not interruption.',
    stagingZh: 'T3 / T4 只把浆膜当观察，要邻帧复核。单帧像断了更像伪像。不定 cT。',
    stagingEn: 'T3 / T4 uses serosa as an observation and needs a neighbor frame. A single-frame break is often artifact. Not a definite cT.',
  },
];

export function guideForFrac(frac: number): WallLayerGuide {
  const f = Math.max(0, Math.min(0.999, Number.isFinite(frac) ? frac : 0));
  return WALL_LAYER_GUIDES.find((item) => f < item.frac1) || WALL_LAYER_GUIDES[WALL_LAYER_GUIDES.length - 1];
}

export function lerpPoint(a: number[], b: number[], t: number): [number, number] {
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
}

export function loadFrameImage(dataUrl: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error('frame decode failed'));
    image.src = dataUrl;
  });
}

export function cropSquareZoom(
  image: HTMLImageElement,
  cx: number,
  cy: number,
  srcSize: number,
  outSize: number,
  stroke?: string,
): string {
  const canvas = document.createElement('canvas');
  canvas.width = outSize;
  canvas.height = outSize;
  const ctx = canvas.getContext('2d');
  if (!ctx) return '';
  ctx.fillStyle = '#020617';
  ctx.fillRect(0, 0, outSize, outSize);
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = 'high';
  const half = srcSize / 2;
  ctx.drawImage(image, cx - half, cy - half, srcSize, srcSize, 0, 0, outSize, outSize);
  ctx.strokeStyle = stroke || 'rgba(248,250,252,0.7)';
  ctx.lineWidth = 1;
  ctx.strokeRect(0.5, 0.5, outSize - 1, outSize - 1);
  ctx.beginPath();
  ctx.moveTo(outSize / 2, 8);
  ctx.lineTo(outSize / 2, outSize - 8);
  ctx.moveTo(8, outSize / 2);
  ctx.lineTo(outSize - 8, outSize / 2);
  ctx.stroke();
  return canvas.toDataURL('image/jpeg', 0.88);
}

export function cropChannelOverview(
  image: HTMLImageElement,
  lesion: number[],
  wall: number[],
  pad: number,
  maxW: number,
  maxH: number,
): string {
  const minX = Math.min(lesion[0], wall[0]) - pad;
  const maxX = Math.max(lesion[0], wall[0]) + pad;
  const minY = Math.min(lesion[1], wall[1]) - pad;
  const maxY = Math.max(lesion[1], wall[1]) + pad;
  const width = Math.max(28, maxX - minX);
  const height = Math.max(28, maxY - minY);
  const scale = Math.min(maxW / width, maxH / height, 5);
  const outW = Math.max(1, Math.round(width * scale));
  const outH = Math.max(1, Math.round(height * scale));
  const canvas = document.createElement('canvas');
  canvas.width = outW;
  canvas.height = outH;
  const ctx = canvas.getContext('2d');
  if (!ctx) return '';
  ctx.fillStyle = '#020617';
  ctx.fillRect(0, 0, outW, outH);
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = 'high';
  ctx.drawImage(image, minX, minY, width, height, 0, 0, outW, outH);
  const mapX = (x: number) => (x - minX) * scale;
  const mapY = (y: number) => (y - minY) * scale;
  ctx.strokeStyle = 'rgba(34,211,238,0.95)';
  ctx.lineWidth = 1.6;
  ctx.beginPath();
  ctx.moveTo(mapX(lesion[0]), mapY(lesion[1]));
  ctx.lineTo(mapX(wall[0]), mapY(wall[1]));
  ctx.stroke();
  ctx.fillStyle = '#22d3ee';
  ctx.strokeStyle = '#fff';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.arc(mapX(lesion[0]), mapY(lesion[1]), 3.4, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();
  ctx.fillStyle = '#fb923c';
  ctx.beginPath();
  ctx.arc(mapX(wall[0]), mapY(wall[1]), 3.4, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();
  return canvas.toDataURL('image/jpeg', 0.88);
}
