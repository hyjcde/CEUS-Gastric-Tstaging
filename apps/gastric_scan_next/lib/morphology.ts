/**
 * 形态学操作工具库
 * 用于前端图像处理，如生成瘤周环
 */

export interface AnnotationShape {
  label: string;
  points: [number, number][];
  shape_type?: string;
}

export interface AnnotationData {
  shapes: AnnotationShape[];
  imageWidth?: number;
  imageHeight?: number;
}

/**
 * 从 JSON 标注文件生成瘤周环 (Peritumoral Ring)
 * 
 * 原理：
 * 1. 从 JSON 读取多边形坐标
 * 2. 在 Canvas 上绘制填充多边形作为掩码
 * 3. 对掩码进行形态学膨胀
 * 4. Ring = Dilate(Mask) - Mask
 * 
 * @param jsonUrl JSON 标注文件的 URL
 * @param imageWidth 图像宽度
 * @param imageHeight 图像高度
 * @param radius 膨胀半径（像素），默认 20px (约 5mm)
 * @param color 环的颜色 [r, g, b, a]
 * @returns Promise<string> 返回生成的瘤周环图像的 Data URL (PNG)
 */
export async function generatePeritumoralRingFromAnnotation(
  jsonUrl: string,
  imageWidth: number,
  imageHeight: number,
  radius: number = 20,
  color: [number, number, number, number] = [255, 165, 0, 200] // Orange color
): Promise<string> {
  // 1. 获取标注数据
  const response = await fetch(jsonUrl);
  if (!response.ok) {
    throw new Error(`Failed to fetch annotation: ${response.status}`);
  }
  const annotationData: AnnotationData = await response.json();
  
  if (!annotationData.shapes || annotationData.shapes.length === 0) {
    throw new Error('No shapes found in annotation');
  }
  
  console.log(`[Morphology] Found ${annotationData.shapes.length} shapes in annotation`);
  
  // 2. 创建 Canvas 并绘制掩码
  const canvas = document.createElement('canvas');
  canvas.width = imageWidth;
  canvas.height = imageHeight;
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  if (!ctx) {
    throw new Error('Could not get canvas context');
  }
  
  // 绘制所有多边形（填充）
  ctx.fillStyle = 'white';
  for (const shape of annotationData.shapes) {
    if (shape.points && shape.points.length >= 3) {
      ctx.beginPath();
      ctx.moveTo(shape.points[0][0], shape.points[0][1]);
      for (let i = 1; i < shape.points.length; i++) {
        ctx.lineTo(shape.points[i][0], shape.points[i][1]);
      }
      ctx.closePath();
      ctx.fill();
    }
  }
  
  // 3. 获取掩码数据
  const maskImageData = ctx.getImageData(0, 0, imageWidth, imageHeight);
  const maskData = maskImageData.data;
  
  // 创建二值掩码
  const binaryMask = new Int8Array(imageWidth * imageHeight);
  let foregroundCount = 0;
  
  for (let i = 0; i < maskData.length; i += 4) {
    // 白色像素 = 前景
    if (maskData[i] > 128) {
      const idx = i / 4;
      binaryMask[idx] = 1;
      foregroundCount++;
    }
  }
  
  console.log(`[Morphology] Foreground pixels: ${foregroundCount} / ${imageWidth * imageHeight}`);
  
  if (foregroundCount === 0) {
    throw new Error('No foreground pixels found in mask');
  }

  // 4. 形态学膨胀 (BFS)
  const queue: number[] = [];
  const distances = new Int16Array(imageWidth * imageHeight).fill(-1);
  
  // 找到边缘前景像素作为 BFS 起点
  for (let y = 0; y < imageHeight; y++) {
    for (let x = 0; x < imageWidth; x++) {
      const idx = y * imageWidth + x;
      if (binaryMask[idx] === 1) {
        // 检查是否是边缘（4邻域有背景）
        let isEdge = false;
        if (x > 0 && binaryMask[idx - 1] === 0) isEdge = true;
        else if (x < imageWidth - 1 && binaryMask[idx + 1] === 0) isEdge = true;
        else if (y > 0 && binaryMask[idx - imageWidth] === 0) isEdge = true;
        else if (y < imageHeight - 1 && binaryMask[idx + imageWidth] === 0) isEdge = true;
        
        if (isEdge) {
          queue.push(idx);
          distances[idx] = 0;
        }
      }
    }
  }
  
  console.log(`[Morphology] Edge pixels for BFS: ${queue.length}`);
  
  // BFS 扩散
  let head = 0;
  while (head < queue.length) {
    const idx = queue[head++];
    const d = distances[idx];
    
    if (d >= radius) continue;
    
    const cx = idx % imageWidth;
    const cy = Math.floor(idx / imageWidth);
    
    const neighbors = [
      { x: cx - 1, y: cy, idx: idx - 1 },
      { x: cx + 1, y: cy, idx: idx + 1 },
      { x: cx, y: cy - 1, idx: idx - imageWidth },
      { x: cx, y: cy + 1, idx: idx + imageWidth }
    ];
    
    for (const n of neighbors) {
      if (n.x >= 0 && n.x < imageWidth && n.y >= 0 && n.y < imageHeight) {
        if (binaryMask[n.idx] === 0 && distances[n.idx] === -1) {
          distances[n.idx] = d + 1;
          queue.push(n.idx);
        }
      }
    }
  }
  
  // 5. 生成环图像
  const ringImageData = ctx.createImageData(imageWidth, imageHeight);
  let ringPixels = 0;
  
  for (let i = 0; i < imageWidth * imageHeight; i++) {
    if (distances[i] > 0 && distances[i] <= radius) {
      const p = i * 4;
      // 渐变效果：内圈更实，外圈更虚
      const alpha = Math.round(color[3] * (1 - (distances[i] - 1) / radius * 0.5));
      ringImageData.data[p] = color[0];
      ringImageData.data[p + 1] = color[1];
      ringImageData.data[p + 2] = color[2];
      ringImageData.data[p + 3] = alpha;
      ringPixels++;
    }
  }
  
  console.log(`[Morphology] Ring pixels generated: ${ringPixels}`);
  
  ctx.putImageData(ringImageData, 0, 0);
  return canvas.toDataURL('image/png');
}

/**
 * 旧版：从掩码图片生成瘤周环（保留兼容性）
 * @deprecated 推荐使用 generatePeritumoralRingFromAnnotation
 */
export async function generatePeritumoralRing(
  maskUrl: string, 
  radius: number = 20,
  color: [number, number, number, number] = [255, 165, 0, 200]
): Promise<string> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.crossOrigin = "Anonymous";
    img.src = maskUrl;
    
    img.onload = async () => {
      try {
        const canvas = document.createElement('canvas');
        const width = img.width;
        const height = img.height;
        canvas.width = width;
        canvas.height = height;
        
        const ctx = canvas.getContext('2d', { willReadFrequently: true });
        if (!ctx) {
          reject(new Error('Could not get canvas context'));
          return;
        }

        ctx.drawImage(img, 0, 0);
        const originalImageData = ctx.getImageData(0, 0, width, height);
        const originalData = originalImageData.data;
        
        const binaryMask = new Int8Array(width * height);
        
        // 提取前景（支持多种格式）
        for (let i = 0; i < originalData.length; i += 4) {
          const r = originalData[i];
          const g = originalData[i + 1];
          const b = originalData[i + 2];
          const a = originalData[i + 3];
          
          // 绿色轮廓检测
          const isForeground = (a > 20 && (r + g + b) > 30) || (g > 50 && g > r && g > b);
          
          if (isForeground) { 
             binaryMask[i / 4] = 1;
          }
        }
        
        let foregroundCount = 0;
        for (let i = 0; i < binaryMask.length; i++) {
          if (binaryMask[i] === 1) foregroundCount++;
        }
        console.log(`[Morphology] Foreground pixels from image: ${foregroundCount}`);
        
        if (foregroundCount === 0) {
          reject(new Error('No foreground pixels found in mask'));
          return;
        }

        // BFS 膨胀
        const queue: number[] = [];
        const distances = new Int16Array(width * height).fill(-1);
        
        for (let y = 0; y < height; y++) {
          for (let x = 0; x < width; x++) {
            const idx = y * width + x;
            if (binaryMask[idx] === 1) {
              let isEdge = false;
              if (x > 0 && binaryMask[idx - 1] === 0) isEdge = true;
              else if (x < width - 1 && binaryMask[idx + 1] === 0) isEdge = true;
              else if (y > 0 && binaryMask[idx - width] === 0) isEdge = true;
              else if (y < height - 1 && binaryMask[idx + width] === 0) isEdge = true;
              
              if (isEdge) {
                queue.push(idx);
                distances[idx] = 0;
              }
            }
          }
        }
        
        let head = 0;
        while (head < queue.length) {
          const idx = queue[head++];
          const d = distances[idx];
          if (d >= radius) continue;
          
          const cx = idx % width;
          const cy = Math.floor(idx / width);
          
          const neighbors = [
            { x: cx - 1, y: cy, idx: idx - 1 },
            { x: cx + 1, y: cy, idx: idx + 1 },
            { x: cx, y: cy - 1, idx: idx - width },
            { x: cx, y: cy + 1, idx: idx + width }
          ];
          
          for (const n of neighbors) {
            if (n.x >= 0 && n.x < width && n.y >= 0 && n.y < height) {
              if (binaryMask[n.idx] === 0 && distances[n.idx] === -1) {
                distances[n.idx] = d + 1;
                queue.push(n.idx);
              }
            }
          }
        }
        
        const ringImageData = ctx.createImageData(width, height);
        for (let i = 0; i < width * height; i++) {
          if (distances[i] > 0 && distances[i] <= radius) {
            const p = i * 4;
            const alpha = Math.round(color[3] * (1 - (distances[i] - 1) / radius * 0.5));
            ringImageData.data[p] = color[0];
            ringImageData.data[p + 1] = color[1];
            ringImageData.data[p + 2] = color[2];
            ringImageData.data[p + 3] = alpha;
          }
        }
        
        ctx.putImageData(ringImageData, 0, 0);
        resolve(canvas.toDataURL('image/png'));
        
      } catch (e) {
        reject(e);
      }
    };
    
    img.onerror = () => reject(new Error('Failed to load mask image'));
  });
}

